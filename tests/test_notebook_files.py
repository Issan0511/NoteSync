import asyncio
import base64
from copy import deepcopy
import json
import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication
from websockets.protocol import State

from notesync.NotebookExports import create_notebook_backup
try:
    from notesync.NotebookText import NoteText
except ImportError:
    NoteText = None
from notesync.NotebookWindow import NotebookWindow
from notesync.WebServer import WebBridge, WebServer


class NotebookFileTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'notes.json'
        for target in ('notesync.WebServer.WebServer.start', 'notesync.WebServer.WebServer.stop',
                       'notesync.NotebookWindow.NotebookBridge'):
            mocked = patch(target, return_value=None, create=True)
            mocked.start()
            self.addCleanup(mocked.stop)
        kwargs = {'store_path': self.path}
        if 'mcp_connection_file' in inspect.signature(NotebookWindow).parameters:
            kwargs['mcp_connection_file'] = Path(self.directory.name) / 'unused-mcp.json'
        self.window = NotebookWindow(**kwargs)
        self.addCleanup(self.window.close)
        self.replies, self.events = [], []
        self.window.web_server.reply_to = lambda client, message: self.replies.append((client, message))
        self.window.web_server.broadcast = self.events.append
        self.client = object()

    def draw(self):
        controller = self.window.controller
        controller.begin_custom_stroke('#3478dc', .005, .8, .2, .2, .4, brush='fountain')
        controller.add_stroke_point(.8, .3, .7)
        controller.end_stroke()
        if NoteText is not None and hasattr(controller, 'serialized_texts'):
            controller.sketchbook_texts = [NoteText(id='original-text', text='補足', norm_x=.2, norm_y=.4)]

    def request(self, action, **data):
        payload = dict(type='note_file', action=action, requestId='private-file',
                       documentId=self.window.store.active_id, **data)
        self.window.web_server._handle_client_message(payload, self.client)
        self.assertIs(self.replies[-1][0], self.client)
        return self.replies[-1][1]


class NotebookFileIntegrationTests(NotebookFileTestCase):
    def test_mixin_integration_retains_text_library_and_mcp_hooks(self):
        self.draw()
        previous = self.window.store.active_id
        self.assertTrue(self.window._on_notebook_command({'type': 'note_library', 'action': 'duplicate'}))
        self.assertNotEqual(self.window.store.active_id, previous)
        self.assertEqual(len(self.window.controller.sketchbook_strokes), 1)
        has_text = NoteText is not None and hasattr(self.window.controller, 'serialized_texts')
        if has_text:
            self.assertEqual(self.window.controller.sketchbook_texts[0].text, '補足')
            self.assertNotEqual(self.window.controller.sketchbook_texts[0].id, 'original-text')
        status = self.window._get_web_status()
        self.assertEqual(status['saveState'], 'saved')
        self.assertEqual(status['notes'][0]['textCount'], 1 if has_text else 0)
        if hasattr(self.window, '_handle_mcp_call'):
            self.assertEqual(self.window._handle_mcp_call('get_note_status', {})['note_id'], status['documentId'])

    def test_png_and_pdf_downloads_only_reply_to_requesting_client(self):
        self.draw()
        self.window.store.active['title'] = '../応用代数:*?'
        for action, prefix, mime in [('png', b'\x89PNG', 'image/png'), ('pdf', b'%PDF-', 'application/pdf')]:
            with self.subTest(action=action):
                reply = self.request(action)
                self.assertTrue(reply['ok'])
                self.assertTrue(reply['saved'])
                self.assertEqual(reply['mime'], mime)
                self.assertTrue(base64.b64decode(reply['data']).startswith(prefix))
                self.assertNotIn('/', reply['filename'])
                self.assertNotIn(':', reply['filename'])
        self.assertFalse(any(event.get('type') == 'note_file_result' for event in self.events))
        self.assertFalse(any('data' in event for event in self.events))

    def test_backup_roundtrip_is_additive_preserves_active_note_and_renews_ids(self):
        self.draw()
        first = self.window.store.active_id
        reply = self.request('backup')
        self.assertTrue(reply['ok'])
        original = deepcopy(self.window.store.active)
        imported = self.request('import', data=reply['data'])
        self.assertTrue(imported['ok'])
        self.assertEqual(imported['importedCount'], 1)
        self.assertEqual(self.window.store.active_id, first)
        self.assertEqual(len(self.window.store.notes), 2)
        copy = next(note for note in self.window.store.notes if note['id'] != first)
        if original.get('texts'):
            self.assertNotEqual(copy['texts'][0]['id'], 'original-text')
            self.assertEqual(copy['texts'][0]['text'], original['texts'][0]['text'])
        self.assertEqual(json.loads(json.dumps(copy['strokes'])), json.loads(json.dumps(original['strokes'])))
        self.assertEqual(len(json.loads(self.path.read_text())['notes']), 2)
        self.assertEqual(len(self.window.controller.sketchbook_strokes), 1)

    def test_backup_whitelists_content_and_export_can_rescue_ink_after_disk_failure(self):
        self.draw()
        self.window.store.active.update(api_key='fake-key-must-not-export', path='/fake/private/path')
        with patch.object(self.window, '_save_notebook_legacy', return_value=False):
            reply = self.request('backup')
        self.assertTrue(reply['ok'])
        self.assertFalse(reply['saved'])
        text = base64.b64decode(reply['data']).decode()
        self.assertNotIn('fake-key-must-not-export', text)
        self.assertNotIn('/fake/private/path', text)
        self.assertEqual(len(json.loads(text)['notes'][0]['strokes']), 1)
        self.assertEqual(self.window._get_web_status()['saveState'], 'error')

    def test_failed_import_save_rolls_back_added_notes_without_changing_current_ink(self):
        self.draw()
        self.window.save_notebook()
        backup = create_notebook_backup(self.window.store.notes, active_id=self.window.store.active_id)
        before = deepcopy(self.window.store.notes)
        active = self.window.store.active_id
        ink = self.window.controller.serialized_ink()
        real_save = self.window._save_notebook_legacy
        calls = 0

        def fail_import_write():
            nonlocal calls
            calls += 1
            return False if calls == 2 else real_save()

        with patch.object(self.window, '_save_notebook_legacy', side_effect=fail_import_write):
            reply = self.request('import', data=base64.b64encode(backup).decode())
        self.assertFalse(reply['ok'])
        self.assertEqual(self.window.store.notes, before)
        self.assertEqual(self.window.store.active_id, active)
        self.assertEqual(self.window.controller.serialized_ink(), ink)
        self.assertEqual(len(json.loads(self.path.read_text())['notes']), 1)

    def test_malformed_import_wrong_document_and_invalid_request_are_private_failures(self):
        self.draw()
        before = deepcopy(self.window.store.notes)
        for encoded in ('invalid base64!', base64.b64encode(b'not json').decode()):
            with self.subTest(encoded=encoded):
                self.assertFalse(self.request('import', data=encoded)['ok'])
                self.assertEqual(self.window.store.notes, before)
        self.window.web_server._handle_client_message(dict(type='note_file', action='png',
                                                          documentId='old-note', requestId='old-page'), self.client)
        self.assertFalse(self.replies[-1][1]['ok'])
        count = len(self.replies)
        self.window.web_server._handle_client_message(dict(type='note_file', action='png', requestId='../invalid'), self.client)
        self.assertEqual(len(self.replies), count)

    def test_route_overwrites_spoofed_reply_target_without_mutating_request(self):
        message = dict(type='note_file', action='backup', requestId='route-test',
                       documentId=self.window.store.active_id, _reply_client='spoofed target')
        self.window.web_server._handle_client_message(message, self.client)
        self.assertIs(self.replies[-1][0], self.client)
        self.assertEqual(message['_reply_client'], 'spoofed target')

    def test_failed_final_save_keeps_window_and_services_open(self):
        event = QCloseEvent()
        with patch.object(self.window, '_save_notebook_legacy', return_value=False), \
                patch.object(self.window.web_server, 'stop') as stop:
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        stop.assert_not_called()

    def test_empty_eraser_gesture_schedules_saved_ack_without_changing_undo(self):
        self.window.save_timer.stop()
        self.events.clear()
        revision = self.window.controller.ink_revision
        self.window._begin_web_erase()
        self.window._on_web_erase_requested(dict(normX=.9, normY=.9, mode='stroke', size=25))
        self.assertFalse(self.window.save_timer.isActive())
        self.window._finish_erase()
        self.assertTrue(self.window.save_timer.isActive())
        self.assertEqual(self.window.save_timer.interval(), 600)
        self.assertEqual(self.window.controller.ink_revision, revision)
        self.assertEqual(self.window.controller.undo_stack, [])
        self.assertIsNone(self.window.controller.pending_edit)
        self.assertFalse(any(event['type'] == 'note_saved' for event in self.events))
        self.window.save_timer.stop()
        self.window.save_timer.timeout.emit()
        self.assertTrue(any(event['type'] == 'note_saved' and event.get('state') == 'saved' for event in self.events))

    def test_noop_selection_transform_schedules_saved_ack_without_new_revision(self):
        self.draw()
        self.window.save_notebook()
        self.window.save_timer.stop()
        self.events.clear()
        revision = self.window.controller.ink_revision
        history = len(self.window.controller.undo_stack)
        self.window._on_notebook_command(dict(type='note_ink_edit', action='transform', indices=[0],
                                               documentId=self.window.store.active_id, baseRevision=revision,
                                               requestId='noop-transform', matrix=[1, 0, 0, 1, 0, 0]))
        result = next(event for event in self.events if event['type'] == 'note_ink_edit_result')
        self.assertTrue(result['ok'])
        self.assertEqual(self.window.controller.ink_revision, revision)
        self.assertEqual(len(self.window.controller.undo_stack), history)
        self.assertTrue(self.window.save_timer.isActive())
        self.assertFalse(any(event['type'] == 'note_saved' for event in self.events))
        self.window.save_timer.stop()
        self.window.save_timer.timeout.emit()
        self.assertTrue(any(event['type'] == 'note_saved' and event.get('state') == 'saved' for event in self.events))

    def test_idle_finish_erase_helpers_do_not_schedule_extra_saves(self):
        self.window.save_timer.stop()
        self.window._finish_erase()
        self.window._finish_erase()
        self.assertFalse(self.window.save_timer.isActive())


class PrivateReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_file_bytes_are_not_sent_to_other_authenticated_clients(self):
        class Socket:
            state = State.OPEN

            def __init__(self):
                self.messages = []

            async def send(self, data):
                self.messages.append(json.loads(data))

        sender, other = Socket(), Socket()
        server = WebServer(WebBridge(), lambda _: None, lambda: {})
        server.ws_loop = asyncio.get_running_loop()
        server.connected_clients = {sender, other}
        message = {'type': 'note_file_result', 'requestId': 'private', 'data': 'private-download-fixture'}
        server.reply_to(sender, message)
        for _ in range(4):
            await asyncio.sleep(0)
        self.assertEqual(sender.messages, [message])
        self.assertEqual(other.messages, [])


class DirectoryNotebookFileTests(NotebookFileTestCase):
    def setUp(self):
        super().setUp()
        from notesync.NotebookModel import NotebookStore
        self.path = Path(self.directory.name) / 'library'
        original = self.window.store
        self.window.store = NotebookStore(self.path)
        self.window.store.notes = deepcopy(original.notes)
        self.window.store.active_id = original.active_id
        self.window.store.save()

    # Run the directory-specific integration checks, without inheriting tests
    # which deliberately read the legacy JSON path themselves.
    def test_attachment_move_duplicate_backup_and_restore(self):
        raw = b'course handout'
        self.assertTrue(self.request('attach', filename='資料.txt', data=base64.b64encode(raw).decode())['ok'])
        note = self.window.store.active; item = note['attachments'][0]
        self.assertNotIn('data', item)
        self.assertTrue(self.window._on_notebook_command(dict(type='note_library', action='course', course='流体力学')))
        self.assertTrue(self.window._on_notebook_command(dict(type='note_library', action='duplicate')))
        copied = self.window.store.active['attachments'][0]
        self.assertNotEqual(item['id'], copied['id'])
        self.assertEqual(base64.b64decode(self.request('attachment_download', attachmentId=copied['id'])['data']), raw)
        backup = self.request('backup')
        self.assertTrue(backup['ok'])
        self.assertTrue(self.request('import', data=backup['data'])['ok'])
        self.assertTrue(self.request('attachment_remove', attachmentId=copied['id'])['ok'])
        self.assertEqual(self.window.store.active['attachments'], [])
        self.assertEqual(self.window.store.read_attachment(note, item['id'])[1], raw)

    def test_attachment_failed_save_rolls_back_and_stays_private(self):
        real_save = self.window._save_notebook_legacy
        count = 0
        def fail_second():
            nonlocal count
            count += 1
            return False if count == 2 else real_save()
        with patch.object(self.window, '_save_notebook_legacy', side_effect=fail_second):
            self.assertFalse(self.request('attach', filename='資料.txt', data=base64.b64encode(b'private data').decode())['ok'])
        self.assertEqual(self.window.store.active.get('attachments', []), [])
        self.assertFalse(any('data' in event for event in self.events))

if __name__ == '__main__':
    unittest.main()
