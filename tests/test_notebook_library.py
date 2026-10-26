from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from beamerplus.NotebookLibrary import NotebookLibraryMixin
from beamerplus.NotebookModel import NotebookController, NotebookStore
try:
    from beamerplus.NotebookText import NoteText
except ImportError:
    NoteText = None


class Label:
    def __init__(self):
        self.text = ''

    def setText(self, text):
        self.text = text


class LibraryHost(NotebookLibraryMixin):
    def __init__(self, path):
        self.store = NotebookStore(path)
        self.controller = NotebookController()
        self.events = []
        self.forwarded = []
        self.legacy_failure = False
        self.legacy_saves = 0
        self.finish_eraser_calls = 0
        self.dirty_calls = 0
        self.timer_starts = 0
        self.save_label = Label()
        self.title_label = Label()
        self.canvas = SimpleNamespace(aspect=4/3, paper='plain', update=lambda: None)
        self.web_server = SimpleNamespace(broadcast=self.events.append)
        self.save_timer = SimpleNamespace(stop=lambda: None, start=self._start_timer)
        self._init_notebook_library()
        self._document_id = self.store.active_id
        if hasattr(self.controller, 'serialized_texts'):
            self.controller.load_ink(self.store.active['strokes'], self.store.active.get('texts'))
        else:
            self.controller.load_ink(self.store.active['strokes'])
        for signal in (self.controller.stroke_finished, self.controller.strokes_updated,
                       self.controller.strokes_cleared, self.controller.texts_updated):
            signal.connect(self._ink_changed)

    def _save_notebook_legacy(self):
        self.legacy_saves += 1
        self.store.active['strokes'] = self.controller.serialized_ink()
        if hasattr(self.controller, 'serialized_texts'):
            self.store.active['texts'] = self.controller.serialized_texts()
        if self.legacy_failure:
            return False
        self.store.save()
        return True

    def _get_web_status_legacy(self):
        return dict(documentId=self.store.active_id, inkRevision=self.controller.ink_revision,
                    sketchbookStrokes=self.controller.serialized_ink(),
                    noteTexts=self.controller.serialized_texts() if hasattr(self.controller, 'serialized_texts') else [])

    def _on_notebook_command_legacy(self, data):
        self.forwarded.append(data)

    def _ink_changed_legacy(self, *args):
        self.dirty_calls += 1

    def _finish_erase(self):
        self.finish_eraser_calls += 1
        self.controller.finish_edit()

    def _start_timer(self):
        self.timer_starts += 1

    def command(self, action, **data):
        return self._on_notebook_command(dict(type='note_library', action=action,
                                               requestId='library-test', **data))

    def draw(self, *, finish=True):
        self.controller.begin_custom_stroke('#202124', .005, .8, .2, .2, .4, brush='fountain')
        self.controller.add_stroke_point(.8, .2, .7)
        if finish:
            self.controller.end_stroke()


class NotebookLibraryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'notes.json'
        self.host = LibraryHost(self.path)

    def test_save_states_timestamp_and_noop_autosave_does_not_touch_updated_at(self):
        with patch('beamerplus.NotebookLibrary._now', return_value='2026-10-26T01:00:00.000Z'):
            self.host.draw()
            updated = self.host.store.active['updatedAt']
            self.assertEqual(self.host._get_web_status()['saveState'], 'dirty')
            self.assertTrue(self.host.save_notebook())
        with patch('beamerplus.NotebookLibrary._now', return_value='2026-10-26T02:00:00.000Z'):
            self.assertTrue(self.host.save_notebook())
        self.assertEqual(self.host.store.active['updatedAt'], updated)
        status = self.host._get_web_status()
        self.assertEqual(status['savedAt'], '2026-10-26T02:00:00.000Z')
        self.assertEqual(status['saveState'], 'saved')
        self.assertIsNone(status['saveError'])
        self.assertEqual(status['notes'][0]['strokeCount'], 1)
        states = [event for event in self.host.events if event['type'] == 'note_save_state']
        self.assertEqual([event['state'] for event in states], ['dirty', 'saving', 'saved', 'saving', 'saved'])
        self.assertTrue(all(event['inkRevision'] == self.host.controller.ink_revision for event in states))

    def test_failed_save_keeps_controller_and_store_ink_and_reports_error(self):
        self.host.draw()
        original = deepcopy(self.host.store.notes)
        strokes = self.host.controller.serialized_ink()
        self.host.legacy_failure = True
        self.assertFalse(self.host.save_notebook())
        self.assertEqual(self.host.store.notes, original)
        self.assertEqual(self.host.controller.serialized_ink(), strokes)
        status = self.host._get_web_status()
        self.assertEqual(status['saveState'], 'error')
        self.assertIn('再試行', status['saveError'])

    def test_failed_flush_blocks_every_switch_and_preserves_live_stroke(self):
        first = self.host.store.active_id
        second = self.host.store.new_note('別のノート')['id']
        self.host.store.active_id = first
        self.host.draw(finish=False)
        self.host.legacy_failure = True
        for command in [dict(type='note_new'), dict(type='note_select', id=second),
                        dict(type='note_library', action='duplicate'), dict(type='note_library', action='trash')]:
            with self.subTest(command=command):
                self.assertFalse(self.host._on_notebook_command(command))
                self.assertEqual(self.host.store.active_id, first)
                self.assertEqual(len(self.host.store.notes), 2)
                self.assertEqual(len(self.host.controller.sketchbook_strokes), 1)
                self.assertFalse(self.host.store.active.get('deletedAt'))
        self.assertIsNone(self.host.controller.current_stroke)
        self.assertGreaterEqual(self.host.finish_eraser_calls, 4)

    @unittest.skipUnless(NoteText is not None, 'Text annotation support is optional')
    def test_duplicate_preserves_complete_content_with_fresh_note_and_text_ids(self):
        self.host.draw()
        self.host.controller.sketchbook_texts = [NoteText(text='補足', id='original-text', norm_x=.2, norm_y=.3)]
        self.host.store.active.update(title='応用代数学', paper='grid', aspect=16/9, importTag='legacy-tag', custom={'keep': True})
        first = self.host.store.active_id
        self.assertTrue(self.host.command('duplicate'))
        copy = self.host.store.active
        original = next(note for note in self.host.store.notes if note['id'] == first)
        self.assertNotEqual(copy['id'], first)
        self.assertEqual(copy['strokes'], original['strokes'])
        self.assertEqual(copy['texts'][0]['text'], '補足')
        self.assertNotEqual(copy['texts'][0]['id'], original['texts'][0]['id'])
        self.assertEqual(copy['paper'], 'grid')
        self.assertEqual(copy['aspect'], 16/9)
        self.assertEqual(copy['custom'], {'keep': True})
        self.assertNotIn('importTag', copy)
        self.assertEqual(self.host.controller.serialized_texts(), copy['texts'])
        self.assertEqual(self.host.canvas.aspect, 16/9)
        self.assertEqual(self.host._document_id, copy['id'])
        disk = json.loads(self.path.read_text())
        self.assertEqual(disk['activeId'], copy['id'])
        self.assertEqual(disk['version'], 1)

    def test_second_write_failure_rolls_back_new_note_without_switching_or_resetting_undo(self):
        self.host.draw()
        first = self.host.store.active_id
        history = deepcopy(self.host.controller.undo_stack)
        real_save = self.host.store.save
        calls = 0

        def fail_candidate():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PermissionError('read only')
            return real_save()

        with patch.object(self.host.store, 'save', side_effect=fail_candidate):
            self.assertFalse(self.host._on_notebook_command({'type': 'note_new'}))
        self.assertEqual(self.host.store.active_id, first)
        self.assertEqual(len(self.host.store.notes), 1)
        self.assertEqual(self.host.controller.undo_stack, history)
        self.assertEqual(len(self.host.controller.sketchbook_strokes), 1)
        self.assertEqual(json.loads(self.path.read_text())['activeId'], first)
        self.assertEqual(self.host._get_web_status()['saveState'], 'error')

    def test_failed_candidate_write_cannot_select_duplicate_or_trash_the_active_note(self):
        self.host.draw()
        first = self.host.store.active_id
        second = self.host.store.new_note('別のノート')['id']
        self.host.store.active_id = first
        self.host.save_notebook()
        for action, data in [('select', {'id': second}), ('duplicate', {}), ('trash', {})]:
            calls = 0
            real_save = self.host.store.save

            def fail_candidate():
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise PermissionError()
                return real_save()

            with self.subTest(action=action), patch.object(self.host.store, 'save', side_effect=fail_candidate):
                self.assertFalse(self.host.command(action, **data))
            self.assertEqual(self.host.store.active_id, first)
            self.assertEqual(self.host._document_id, first)
            self.assertEqual(len(self.host.store.notes), 2)
            self.assertEqual(len(self.host.controller.sketchbook_strokes), 1)
            self.assertFalse(self.host.store.active.get('deletedAt'))
            self.assertEqual(json.loads(self.path.read_text())['activeId'], first)

    def test_autosave_preserves_an_ongoing_eraser_transaction_and_manual_save_finishes_it(self):
        self.host.draw()
        original = self.host.controller.serialized_ink()
        self.host.controller.erase_at_point(.4, .2, .02, 4/3, 'partial')
        self.assertIsNotNone(self.host.controller.pending_edit)
        self.assertTrue(self.host.save_notebook())
        self.assertIsNotNone(self.host.controller.pending_edit)
        self.assertEqual(self.host.finish_eraser_calls, 0)
        self.host.controller.erase_at_point(.6, .2, .02, 4/3, 'partial')
        self.assertTrue(self.host.command('save'))
        self.assertIsNone(self.host.controller.pending_edit)
        self.host.controller.undo()
        self.assertEqual(self.host.controller.serialized_ink(), original)

    def test_failed_trash_or_rename_rolls_back_metadata_after_successful_flush(self):
        self.host.draw()
        first = self.host.store.active_id
        title = self.host.store.active['title']
        for action, data in [('trash', {}), ('rename', {'title': '保存できない名前'})]:
            real_save = self.host.store.save
            calls = 0

            def fail_candidate():
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise PermissionError()
                return real_save()

            with self.subTest(action=action), patch.object(self.host.store, 'save', side_effect=fail_candidate):
                self.assertFalse(self.host.command(action, **data))
            self.assertEqual(self.host.store.active_id, first)
            self.assertEqual(self.host.store.active['title'], title)
            self.assertIsNone(self.host.store.active['deletedAt'])
            self.assertEqual(len(self.host.store.notes), 1)

    def test_trash_last_note_creates_blank_and_restore_recovers_full_original(self):
        self.host.draw()
        first = self.host.store.active_id
        strokes = self.host.controller.serialized_ink()
        self.assertTrue(self.host.command('trash'))
        blank = self.host.store.active_id
        self.assertNotEqual(blank, first)
        self.assertEqual(self.host.controller.serialized_ink(), [])
        trashed = next(note for note in self.host.store.notes if note['id'] == first)
        self.assertTrue(trashed['deletedAt'])
        self.assertEqual(trashed['strokes'], strokes)
        self.assertFalse(self.host._on_notebook_command(dict(type='note_select', id=first)))
        self.assertEqual(self.host.store.active_id, blank)
        self.assertTrue(self.host.command('restore', id=first))
        self.assertEqual(self.host.store.active_id, blank)
        self.assertTrue(self.host._on_notebook_command(dict(type='note_select', id=first)))
        self.assertEqual(self.host.controller.serialized_ink(), strokes)

    def test_rename_targets_requested_note_without_changing_active_note(self):
        first = self.host.store.active_id
        other = self.host.store.new_note('別のノート')['id']
        self.host.store.active_id = first
        self.assertTrue(self.host.command('rename', id=other, title='  線形代数  '))
        self.assertEqual(self.host.store.active_id, first)
        self.assertEqual(next(note for note in self.host.store.notes if note['id'] == other)['title'], '線形代数')
        self.assertNotEqual(self.host.title_label.text, '線形代数')

    def test_migration_keeps_unknown_fields_and_never_opens_trashed_active_note(self):
        self.host.draw()
        self.host.save_notebook()
        data = json.loads(self.path.read_text())
        first = data['notes'][0]
        first.pop('createdAt')
        first.pop('updatedAt')
        first.update(deletedAt='2026-10-25T01:00:00.000Z', custom={'keep': 'yes'})
        self.path.write_text(json.dumps(data))
        loaded = LibraryHost(self.path)
        self.assertNotEqual(loaded.store.active_id, first['id'])
        old = next(note for note in loaded.store.notes if note['id'] == first['id'])
        self.assertEqual(old['strokes'], first['strokes'])
        self.assertEqual(old['custom'], first['custom'])
        self.assertTrue(old['createdAt'])
        self.assertTrue(old['updatedAt'])
        self.assertTrue(loaded.save_notebook())
        self.assertEqual(len(json.loads(self.path.read_text())['notes']), 2)

    def test_results_precede_state_sync_and_unrelated_commands_keep_legacy_handler(self):
        self.assertTrue(self.host.command('save'))
        self.assertEqual([event['type'] for event in self.host.events[-2:]], ['note_library_result', 'state_sync'])
        result = self.host.events[-2]
        self.assertEqual(result['requestId'], 'library-test')
        self.assertTrue(result['ok'])
        message = dict(type='note_ink_edit', action='delete')
        self.host._on_notebook_command(message)
        self.assertEqual(self.host.forwarded, [message])

    def test_legacy_controller_without_note_text_support_can_duplicate_and_load(self):
        class LegacyController:
            ink_revision = 0
            sketchbook_strokes = []

            def __init__(self):
                self.loaded = []

            def serialized_ink(self):
                return []

            def load_ink(self, strokes):
                self.loaded.append(strokes)

            def end_stroke(self):
                pass

            def finish_edit(self):
                pass

        self.host.controller = LegacyController()
        self.assertTrue(self.host.command('duplicate'))
        self.assertEqual(self.host.controller.loaded, [[]])
        self.assertEqual(self.host.library_metadata()[0]['textCount'], 0)

    def test_checkpoint_validation_queues_only_current_note_and_does_not_finish_input(self):
        active = self.host.store.active_id
        for identifier, document in [('', active), ('invalid/id', active), ('a' * 81, active),
                                     (None, active), ('valid', 'old-note')]:
            self.assertFalse(self.host._on_notebook_command(dict(type='note_save_checkpoint',
                                                                 requestId=identifier, documentId=document)))
        self.assertEqual(self.host._library_save_checkpoints, [])
        self.assertEqual(self.host.timer_starts, 0)
        self.host.draw(finish=False)
        stroke = self.host.controller.current_stroke
        self.assertTrue(self.host._on_notebook_command(dict(type='note_save_checkpoint',
                                                            requestId='checkpoint_1-valid', documentId=active)))
        self.host._init_notebook_library()
        self.assertEqual(self.host._library_save_checkpoints, [(active, 'checkpoint_1-valid')])
        self.assertEqual(self.host.timer_starts, 1)
        self.assertIs(self.host.controller.current_stroke, stroke)
        self.assertEqual(self.host.finish_eraser_calls, 0)
        self.assertEqual(self.host.legacy_saves, 0)
        self.assertEqual(self.host.forwarded, [])

    def test_successful_save_acknowledges_checkpoints_in_both_payloads_once(self):
        active = self.host.store.active_id
        for request_id in ('checkpoint-1', 'checkpoint-2', 'checkpoint-2'):
            self.host._on_notebook_command(dict(type='note_save_checkpoint', requestId=request_id,
                                                documentId=active))
        self.assertTrue(self.host.save_notebook())
        saved = [event for event in self.host.events if event.get('state') == 'saved']
        self.assertEqual([event['type'] for event in saved], ['note_save_state', 'note_saved'])
        self.assertTrue(all(event['saveCheckpoints'] == ['checkpoint-1', 'checkpoint-2'] for event in saved))
        self.assertTrue(all(event['noteId'] == active for event in saved))
        self.assertEqual(self.host._library_save_checkpoints, [])
        self.host.events.clear()
        self.assertTrue(self.host.save_notebook())
        self.assertTrue(all(event['saveCheckpoints'] == [] for event in self.host.events
                            if event['type'] in ('note_save_state', 'note_saved')))

    def test_failed_save_retains_checkpoints_until_successful_retry(self):
        active = self.host.store.active_id
        self.host._on_notebook_command(dict(type='note_save_checkpoint', requestId='retry-me', documentId=active))
        self.host.legacy_failure = True
        self.assertFalse(self.host.save_notebook())
        self.assertEqual(self.host._library_save_checkpoints, [(active, 'retry-me')])
        self.assertFalse(any(event.get('state') == 'saved' for event in self.host.events))
        self.assertTrue(all(event['saveCheckpoints'] == [] for event in self.host.events
                            if event['type'] == 'note_save_state'))
        self.host.legacy_failure = False
        self.assertTrue(self.host.save_notebook())
        self.assertEqual(self.host.events[-1]['saveCheckpoints'], ['retry-me'])
        self.assertEqual(self.host._library_save_checkpoints, [])

    def test_switch_flush_acknowledges_old_note_checkpoints_before_new_note_saved(self):
        active = self.host.store.active_id
        self.host._on_notebook_command(dict(type='note_save_checkpoint', requestId='old-note-input', documentId=active))
        self.assertTrue(self.host.command('new'))
        saved = [event for event in self.host.events if event['type'] == 'note_saved']
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]['noteId'], active)
        self.assertEqual(saved[0]['saveCheckpoints'], ['old-note-input'])
        self.assertNotEqual(saved[1]['noteId'], active)
        self.assertEqual(saved[1]['saveCheckpoints'], [])
        self.assertEqual(self.host._library_save_checkpoints, [])

    def test_checkpoint_storage_is_bounded_to_most_recent_64_unique_requests(self):
        active = self.host.store.active_id
        for number in range(70):
            self.host._on_notebook_command(dict(type='note_save_checkpoint', requestId=f'checkpoint-{number}',
                                                documentId=active))
        self.assertEqual(len(self.host._library_save_checkpoints), 64)
        self.assertEqual(self.host._library_save_checkpoints[0], (active, 'checkpoint-6'))
        self.assertEqual(self.host._library_save_checkpoints[-1], (active, 'checkpoint-69'))


if __name__ == '__main__':
    unittest.main()
