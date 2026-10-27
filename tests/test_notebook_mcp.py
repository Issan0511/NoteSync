import asyncio
import base64
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

from beamerplus.NotebookMCP import NotebookClient
from beamerplus.NotebookWindow import NotebookWindow


class NotebookMCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        start = patch('beamerplus.WebServer.WebServer.start')
        stop = patch('beamerplus.WebServer.WebServer.stop')
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

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Install the optional MCP dependency to run protocol tests')
    def test_submission_source_flushes_saved_note_without_switching_pages(self):
        from beamerplus.NotebookStorage import note_digest
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


    def test_real_stdio_mcp_discovery_image_and_undoable_write(self):
        import sys
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def protocol():
            parameters = StdioServerParameters(command=sys.executable,
                                                args=['-m', 'beamerplus.NotebookMCP', '--connection-file', str(self.path / 'connection.json')])
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    self.assertEqual(names, {'read_current_note', 'get_note_status', 'add_note_text', 'remove_note_text'})
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
