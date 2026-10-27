import asyncio
import base64
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from notesync.NotebookMCP import NotebookClient
from notesync.NotebookWindow import NotebookWindow


class NotebookMCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        start = patch('notesync.WebServer.WebServer.start')
        stop = patch('notesync.WebServer.WebServer.stop')
        start.start()
        stop.start()
        self.addCleanup(start.stop)
        self.addCleanup(stop.stop)
        self.window = NotebookWindow(store_path=self.path / 'notes.json', mcp_connection_file=self.path / 'connection.json')
        self.addCleanup(self.window.close)
        self.client = NotebookClient(self.path / 'connection.json')

    def call_in_worker(self, function):
        result, errors = [], []

        def run():
            try:
                result.append(function())
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        deadline = time.monotonic() + 30
        while worker.is_alive() and time.monotonic() < deadline:
            self.app.processEvents()
            worker.join(.005)
        self.assertFalse(worker.is_alive(), 'MCP request did not finish')
        if errors:
            raise errors[0]
        return result[0]

    def test_loopback_authentication_live_image_write_sync_and_persistence(self):
        if os.name == 'posix':
            self.assertEqual((self.path / 'connection.json').stat().st_mode & 0o777, 0o600)
        descriptor = json.loads((self.path / 'connection.json').read_text())
        descriptor['token'] = 'invalid_' * 6
        wrong_file = self.path / 'wrong.json'
        wrong_file.write_text(json.dumps(descriptor))
        with self.assertRaisesRegex(ValueError, '認証'):
            self.call_in_worker(lambda: NotebookClient(wrong_file).call('get_note_status'))
        events = []
        self.window.web_server.broadcast = events.append
        read = self.call_in_worker(lambda: self.client.call('read_current_note'))
        self.assertTrue(base64.b64decode(read['image']).startswith(b'\x89PNG'))
        result = self.call_in_worker(lambda: self.client.call('add_note_text', note_id=read['note_id'], revision=read['revision'],
                                                             text='まず x ≠ 0 を確認しよう。', norm_x=.55, norm_y=.35))
        self.assertTrue(result['saved'])
        self.assertEqual(result['texts'][0]['color'], '#000000')
        self.assertNotEqual(result['revision'], read['revision'])
        self.assertTrue(any(event['type'] == 'note_texts_updated' and event['texts'] for event in events))
        saved = json.loads((self.path / 'notes.json').read_text())
        self.assertEqual(saved['notes'][0]['texts'][0]['id'], result['text_id'])
        updated = self.call_in_worker(lambda: self.client.call('read_current_note'))
        self.assertNotEqual(updated['image'], read['image'])
        with self.assertRaisesRegex(ValueError, '更新'):
            self.call_in_worker(lambda: self.client.call('remove_note_text', note_id=read['note_id'], revision=read['revision'], text_id=result['text_id']))
        self.assertEqual(len(self.window.controller.sketchbook_texts), 1)
        self.call_in_worker(lambda: self.client.call('remove_note_text', note_id=updated['note_id'], revision=updated['revision'], text_id=result['text_id']))
        self.window.controller.undo()
        self.assertEqual(self.window.controller.sketchbook_texts[0].id, result['text_id'])

    def test_page_switch_and_ongoing_pen_cannot_receive_old_annotations(self):
        original = self.window._handle_mcp_call('get_note_status', {})
        self.window._on_notebook_command({'type': 'note_new'})
        with self.assertRaisesRegex(ValueError, '更新'):
            self.window._handle_mcp_call('add_note_text', dict(original, text='別のページに書かない', norm_x=.2, norm_y=.2))
        controller = self.window.controller
        controller.begin_custom_stroke('#202124', .005, 1, .1, .2)
        current = self.window._handle_mcp_call('get_note_status', {})
        stroke = controller.current_stroke
        with self.assertRaisesRegex(ValueError, '筆記'):
            self.window._handle_mcp_call('add_note_text', dict(current, text='ペンを邪魔しない', norm_x=.2, norm_y=.2))
        self.assertIs(controller.current_stroke, stroke)
        self.assertEqual(controller.sketchbook_texts, [])

    def test_submission_source_flushes_saved_note_without_switching_pages(self):
        from notesync.NotebookStorage import note_digest
        note_id = self.window.store.active['id']
        controller = self.window.controller
        controller.begin_custom_stroke('#000000', .005, 1, .1, .2)
        with self.assertRaisesRegex(ValueError, '筆記'):
            self.window._handle_mcp_call('save_note_snapshot', {'note_id': note_id})
        controller.end_stroke()
        result = self.call_in_worker(lambda: self.client.call('save_note_snapshot', note_id=note_id))
        self.assertTrue(result['saved'])
        self.assertEqual(result['store_path'], str(self.path / 'notes.json'))
        saved = json.loads((self.path / 'notes.json').read_text())['notes'][0]
        self.assertEqual(result['content_hash'], note_digest(saved))
        self.assertEqual(self.window.store.active['id'], note_id)

    def test_reading_other_page_preserves_display_pen_history_and_saved_file(self):
        controller = self.window.controller
        controller.begin_custom_stroke('#000000', .005, 1, .1, .2)
        controller.add_stroke_point(.3, .22)
        controller.end_stroke()
        first = self.window._mcp_metadata()
        self.assertTrue(self.window._on_notebook_command(dict(type='note_page', action='add',
                        documentId=first['page_id'])))
        second_id = self.window.store.active_page['id']
        controller.begin_custom_stroke('#ff0000', .005, 1, .2, .4)
        saved = (self.path / 'notes.json').read_bytes()
        history = deepcopy(controller.undo_stack)
        ink = deepcopy(controller.serialized_ink())
        pen = controller.current_stroke
        pages = self.call_in_worker(lambda: self.client.call('list_note_pages'))
        self.assertEqual(len(pages['pages']), 2)
        self.assertEqual(pages['displayed_page_id'], second_id)
        read = self.call_in_worker(lambda: self.client.call('read_note_page',
                         page_id=first['page_id'], note_id=first['note_id']))
        self.assertFalse(read['current_page'])
        self.assertEqual(read['stroke_count'], 1)
        self.assertTrue(base64.b64decode(read['image']).startswith(b'\x89PNG'))
        self.assertEqual(self.window.store.active_page['id'], second_id)
        self.assertIs(controller.current_stroke, pen)
        self.assertEqual(controller.serialized_ink(), ink)
        self.assertEqual(controller.undo_stack, history)
        self.assertEqual((self.path / 'notes.json').read_bytes(), saved)
        with self.assertRaisesRegex(ValueError, '更新'):
            self.window._handle_mcp_call('add_note_text', dict(read, text='hidden page cannot authorize a write',
                                                             norm_x=.2, norm_y=.2))
        with self.assertRaisesRegex(ValueError, 'ページ'):
            self.window._handle_mcp_call('read_note_page', dict(page_id='missing'))
        with self.assertRaisesRegex(ValueError, 'ノートが切り替わりました'):
            self.window._handle_mcp_call('read_note_page', dict(page_id=first['page_id'], note_id='other'))

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Install the optional MCP dependency to run protocol tests')
    def test_stdio_silent_observation_subscription_and_wait_for_next(self):
        import sys
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from pydantic import AnyUrl

        async def protocol():
            from notesync.NotebookObservation import OBSERVATION_URI
            notified = asyncio.Event()

            async def on_message(message):
                root = getattr(message, 'root', None)
                if getattr(root, 'method', None) == 'notifications/resources/updated':
                    notified.set()

            code = ("import sys; from notesync.NotebookMCP import create_server; "
                    "create_server(sys.argv[1], observation_interval=.05).run(transport='stdio')")
            parameters = StdioServerParameters(command=sys.executable,
                           args=['-c', code, str(self.path / 'connection.json')])
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer, message_handler=on_message) as session:
                    await session.initialize()
                    resources = await session.list_resources()
                    self.assertIn(OBSERVATION_URI, {str(resource.uri) for resource in resources.resources})
                    await session.subscribe_resource(AnyUrl(OBSERVATION_URI))
                    await asyncio.wait_for(notified.wait(), 3)
                    first = await session.call_tool('read_note_observation', {'include_image': False})
                    self.assertTrue(all(part.type == 'text' for part in first.content))
                    before = json.loads(first.content[0].text)
                    self.assertTrue(before['silent'])
                    self.assertFalse(before['model_inference'])
                    self.assertEqual(before['status'], 'ok')
                    result = await session.call_tool('read_note_observation', {'wait_for_next': True})
                    self.assertFalse(result.isError)
                    self.assertTrue(any(part.type == 'image' for part in result.content))
                    after = json.loads(result.content[0].text)
                    self.assertGreater(after['sequence'], before['sequence'])
                    resource = await session.read_resource(AnyUrl(OBSERVATION_URI))
                    self.assertTrue(json.loads(resource.contents[0].text)['silent'])
                    await session.unsubscribe_resource(AnyUrl(OBSERVATION_URI))

        before = deepcopy(self.window.controller.serialized_ink())
        self.call_in_worker(lambda: asyncio.run(protocol()))
        self.assertEqual(self.window.controller.serialized_ink(), before)
        self.assertEqual(self.window.controller.serialized_texts(), [])

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Install the optional MCP dependency to run protocol tests')
    def test_real_stdio_mcp_discovery_image_and_undoable_write(self):
        import sys
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def protocol():
            parameters = StdioServerParameters(command=sys.executable,
                                                args=['-m', 'notesync.NotebookMCP', '--connection-file', str(self.path / 'connection.json')])
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    self.assertEqual(names, {'read_current_note', 'get_note_status', 'read_note_context',
                                            'list_note_pages', 'read_note_page', 'read_note_observation',
                                            'add_note_text', 'remove_note_text'})
                    added_tool = next(tool for tool in tools.tools if tool.name == 'add_note_text')
                    self.assertEqual(added_tool.inputSchema['properties']['color']['default'], '#000000')
                    self.assertTrue(session.get_server_capabilities().resources.subscribe)
                    context = await session.call_tool('read_note_context')
                    self.assertFalse(context.isError)
                    self.assertTrue(all(part.type == 'text' for part in context.content))
                    self.assertEqual(json.loads(context.content[0].text)['status'], 'unavailable')
                    image = await session.call_tool('read_current_note')
                    self.assertFalse(image.isError)
                    self.assertTrue(any(part.type == 'image' and part.mimeType == 'image/png' for part in image.content))
                    status = await session.call_tool('get_note_status')
                    metadata = json.loads(status.content[0].text)
                    added = await session.call_tool('add_note_text', {'note_id': metadata['note_id'], 'revision': metadata['revision'],
                                                                    'text': '両辺から 3 を引こう。', 'x': .5, 'y': .5})
                    self.assertFalse(added.isError)
                    result = json.loads(added.content[0].text)
                    self.assertTrue(result['saved'])
                    stale = await session.call_tool('add_note_text', {'note_id': metadata['note_id'], 'revision': metadata['revision'],
                                                                    'text': '古い画像では書かない', 'x': .5, 'y': .6})
                    self.assertTrue(stale.isError)

        self.call_in_worker(lambda: asyncio.run(protocol()))
        self.assertEqual(len(self.window.controller.sketchbook_texts), 1)
        self.window.controller.undo()
        self.assertEqual(self.window.controller.sketchbook_texts, [])


if __name__ == '__main__':
    unittest.main()
