"""Transactions behind the continuous notebook's per-paper menu."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from beamerplus.NotebookExports import create_notebook_backup, parse_notebook_backup
from test_notebook_pages import PageHost, text


class PageActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'notes.json'
        self.host = PageHost(self.path)
        self.host.draw()
        self.host.store.active['texts'] = [text()]
        self.host.controller.load_ink(self.host.controller.serialized_ink(), [text()])
        self.host.save_notebook()
        self.first = self.host.store.active_page['id']
        self.host.command('add')
        self.second = self.host.store.active_page['id']
        self.host.draw()
        self.host.save_notebook()

    def test_new_notes_and_inserted_pages_are_portrait_without_changing_existing_pages(self):
        self.assertEqual(self.host.store.active_page['aspect'], .75)
        self.host.store.active['aspect'] = 16/9
        self.host.save_notebook()
        self.assertTrue(self.host.command('add', pageId=self.first))
        pages = self.host.store.active['pages']
        self.assertEqual([p['id'] for p in pages][0::2], [self.first, self.second])
        self.assertEqual(pages[1]['aspect'], .75)
        self.assertEqual(pages[2]['aspect'], 16/9)
        self.host.store.new_note()
        self.assertEqual(self.host.store.active['aspect'], .75)

    def test_copy_and_paste_inactive_page_keep_current_undo_and_renew_text_ids(self):
        undo = deepcopy(self.host.controller.undo_stack)
        self.assertTrue(self.host.command('copy', pageId=self.first))
        self.assertEqual(self.host.store.active_page['id'], self.second)
        self.assertEqual(self.host.controller.undo_stack, undo)
        self.assertTrue(self.host._get_web_status()['canPastePage'])
        self.assertTrue(self.host.command('paste', pageId=self.second))
        pasted = self.host.store.active_page
        original = self.host.store.active['pages'][0]
        self.assertEqual(len(self.host.store.active['pages']), 3)
        self.assertNotIn(pasted['id'], (self.first, self.second))
        self.assertEqual(pasted['strokes'], original['strokes'])
        self.assertNotEqual(pasted['texts'][0]['id'], original['texts'][0]['id'])
        self.assertEqual(pasted['texts'][0]['text'], original['texts'][0]['text'])

    def test_cut_is_pasteable_and_delete_can_be_restored_after_restart(self):
        original = deepcopy(self.host.store.active['pages'][0])
        self.assertTrue(self.host.command('cut', pageId=self.first))
        self.assertEqual(len(self.host.store.active['pages']), 1)
        self.assertEqual(self.host.store.active_page['id'], self.second)
        self.assertTrue(self.host._get_web_status()['canRestorePage'])
        loaded = PageHost(self.path)
        self.assertTrue(loaded.command('restore'))
        self.assertEqual(json.loads(json.dumps(loaded.store.active_page)), json.loads(json.dumps(original)))
        self.assertEqual(loaded.store.active['pages'][0]['id'], self.first)
        self.assertEqual(len(loaded.controller.sketchbook_texts), 1)

    def test_clear_removes_text_and_ink_and_restoration_keeps_newer_ink_recoverable(self):
        self.assertTrue(self.host.command('clear', pageId=self.first))
        cleared = self.host.store.active['pages'][0]
        self.assertEqual(cleared['strokes'], [])
        self.assertEqual(cleared['texts'], [])
        self.assertEqual(self.host.store.active_page['id'], self.second)
        self.assertTrue(self.host.command('restore'))
        self.assertEqual(self.host.store.active_page['id'], self.first)
        self.assertEqual(len(self.host.store.active_page['texts']), 1)
        self.assertEqual(len(self.host.store.active_page['strokes']), 1)
        self.assertTrue(self.host.command('restore'))
        self.assertEqual(self.host.store.active_page['texts'], [])

    def test_deleting_last_page_keeps_an_editable_blank_and_restorable_original(self):
        self.assertTrue(self.host.command('delete', pageId=self.first))
        self.assertTrue(self.host.command('delete', pageId=self.second))
        self.assertEqual(len(self.host.store.active['pages']), 1)
        self.assertEqual(self.host.controller.serialized_ink(), [])
        self.assertTrue(self.host.command('restore'))
        self.assertEqual(self.host.store.active_page['id'], self.second)
        self.assertEqual(len(self.host.controller.serialized_ink()), 1)

    def test_failed_candidate_write_rolls_back_clipboard_pages_and_restore_history(self):
        for action in ('copy', 'cut', 'clear', 'delete', 'add'):
            before = deepcopy(self.host.store.notes)
            history = deepcopy(self.host.controller.undo_stack)
            clipboard = deepcopy(getattr(self.host, '_page_clipboard', None))
            real_save = self.host.store.save
            calls = 0

            def fail_candidate():
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('simulated write failure')
                return real_save()

            with self.subTest(action=action), patch.object(self.host.store, 'save', side_effect=fail_candidate):
                self.assertFalse(self.host.command(action, pageId=self.first))
            self.assertEqual(self.host.store.notes, before)
            self.assertEqual(self.host.controller.undo_stack, history)
            self.assertEqual(getattr(self.host, '_page_clipboard', None), clipboard)

    def test_preview_is_requester_only_and_does_not_finish_pen_or_change_page(self):
        replies = []
        self.host.web_server.reply_to = lambda client, data: replies.append((client, data))
        self.host.draw(finish=False)
        active_stroke = self.host.controller.current_stroke
        self.host.events.clear()
        self.assertTrue(self.host._on_notebook_command(dict(type='note_page_preview', requestId='preview-1',
                       notebookId=self.host.store.active_id, pageId=self.first, _reply_client='reader')))
        client, reply = replies[-1]
        self.assertEqual(client, 'reader')
        self.assertTrue(reply['ok'])
        self.assertEqual(len(reply['strokes']), 1)
        self.assertEqual(reply['texts'][0]['text'], text()['text'])
        self.host.store.active['pages'][0]['texts'][0]['text'] = '$x^2$'
        self.assertTrue(self.host._page_preview(dict(notebookId=self.host.store.active_id, pageId=self.first)))
        self.assertIn('renderedSvg', replies[-1][1]['texts'][0])
        self.assertEqual(self.host.store.active_page['id'], self.second)
        self.assertIs(self.host.controller.current_stroke, active_stroke)
        self.assertEqual(self.host.events, [])
        self.assertFalse(self.host._page_preview(dict(notebookId='old-book', pageId=self.first)))

    def test_backup_and_import_preserve_deleted_pages_and_map_clear_targets_to_fresh_ids(self):
        self.host.command('delete', pageId=self.first)
        self.host.command('clear', pageId=self.second)
        backup = create_notebook_backup(self.host.store.notes)
        imported = parse_notebook_backup(backup)['notes'][0]
        self.assertEqual(len(imported['pageTrash']), 2)
        self.assertEqual(imported['pageTrash'][1]['page']['id'], imported['pages'][0]['id'])
        self.assertNotEqual(imported['pageTrash'][0]['page']['id'], self.first)
        self.assertEqual(len(imported['pageTrash'][0]['page']['texts']), 1)
        self.host.store.notes = [imported]
        self.host.store.active_id = imported['id']
        self.host.store.save()
        restored = PageHost(self.path)
        self.assertTrue(restored.command('restore'))
        self.assertEqual(len(restored.controller.serialized_ink()), 1)
        # Clear restore is a reversible swap; consume it to test the deleted entry.
        restored.store.active['pageTrash'].pop()
        self.assertTrue(restored.command('restore'))
        self.assertEqual(len(restored.controller.serialized_texts()), 1)


if __name__ == '__main__':
    unittest.main()
