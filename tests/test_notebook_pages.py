from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from beamerplus.NotebookLibrary import NotebookLibraryMixin
from beamerplus.NotebookModel import NotebookController, NotebookStore
from beamerplus.NotebookPages import NotebookPagesMixin
from beamerplus.NotebookText import NoteText


def stroke():
    return {'color': '#3478dc', 'brush': 'fountain', 'width_ratio': .005, 'opacity': .8,
            'points': [[.2, .2, .4], [.8, .3, .7]]}


def text():
    return asdict(NoteText(text='ページの補足', id='annotation-1', norm_x=.2, norm_y=.4, size=18))


class Label:
    def setText(self, value):
        self.text = value


class PageHost(NotebookPagesMixin, NotebookLibraryMixin):
    def __init__(self, path):
        self.store = NotebookStore(path)
        self.controller = NotebookController()
        self.events, self.routed, self.forwarded = [], [], []
        self.legacy_failure = False
        self.finish_calls = 0
        self.canvas = SimpleNamespace(aspect=4/3, paper='plain', update=lambda: None)
        self.title_label, self.save_label = Label(), Label()
        self.save_timer = SimpleNamespace(stop=lambda: None, start=lambda: None)
        self.web_server = SimpleNamespace(broadcast=self.events.append,
                                          _handle_client_message=self.routed.append)
        self._init_notebook_library()
        self._document_id = self.store.active_page['id']
        self.controller.load_ink(self.store.active['strokes'], self.store.active.get('texts'))
        for signal in (self.controller.stroke_finished, self.controller.strokes_updated,
                       self.controller.strokes_cleared, self.controller.texts_updated):
            signal.connect(self._ink_changed)

    def _save_notebook_legacy(self):
        self.store.active['strokes'] = self.controller.serialized_ink()
        self.store.active['texts'] = self.controller.serialized_texts()
        if self.legacy_failure:
            return False
        self.store.save()
        return True

    def _get_web_status_legacy(self):
        return {'documentId': self._document_id, 'inkRevision': self.controller.ink_revision,
                'sketchbookStrokes': self.controller.serialized_ink(),
                'noteTexts': self.controller.serialized_texts()}

    def _on_notebook_command_legacy(self, data):
        self.forwarded.append(data)

    def _ink_changed_legacy(self, *args):
        pass

    def _finish_erase(self):
        self.finish_calls += 1
        self.controller.finish_edit()

    def command(self, action, **data):
        return self._on_notebook_command(dict(type='note_page', action=action, requestId='page-test',
                                               documentId=self.store.active_page['id'], **data))

    def draw(self, *, finish=True):
        self.controller.begin_custom_stroke('#3478dc', .005, .8, .2, .2, .4, brush='fountain')
        self.controller.add_stroke_point(.8, .3, .7)
        if finish:
            self.controller.end_stroke()


class NotebookPageStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'notes.json'

    def test_legacy_note_migrates_losslessly_and_keeps_old_document_identity(self):
        note = {'id': 'original-note', 'title': '応用代数学', 'strokes': [stroke()],
                'texts': [text()], 'paper': 'grid', 'aspect': 16/9, 'custom': {'preserve': True}}
        original = deepcopy(note)
        self.path.write_text(json.dumps({'version': 1, 'activeId': note['id'], 'notes': [note]}))
        store = NotebookStore(self.path)
        self.assertEqual(store.active_page['id'], 'original-note')
        self.assertEqual(store.active['activePageId'], 'original-note')
        self.assertEqual(len(store.active['pages']), 1)
        for key in ('strokes', 'texts', 'paper', 'aspect'):
            self.assertEqual(store.active_page[key], original[key])
            self.assertEqual(store.active[key], original[key])
        self.assertEqual(store.active['custom'], original['custom'])
        store.save()
        self.assertEqual(json.loads(self.path.read_text())['version'], 1)

    def test_new_page_inherits_paper_and_keeps_ink_and_text_separate_after_reload(self):
        store = NotebookStore(self.path)
        first = store.active_page['id']
        store.active.update(strokes=[stroke()], texts=[text()], paper='ruled', aspect=.75)
        second = store.new_page()['id']
        self.assertNotEqual(first, second)
        self.assertEqual(store.active_page['strokes'], [])
        self.assertEqual(store.active_page['texts'], [])
        self.assertEqual(store.active['paper'], 'ruled')
        self.assertEqual(store.active['aspect'], .75)
        other = stroke()
        other['points'] = [[.3, .4, .9]]
        store.active['strokes'] = [other]
        store.save()
        loaded = NotebookStore(self.path)
        self.assertEqual(loaded.active_page['id'], second)
        self.assertEqual(loaded.active['strokes'], [other])
        loaded.select_page(first)
        self.assertEqual(loaded.active['strokes'], [stroke()])
        self.assertEqual(loaded.active['texts'], [text()])
        loaded.select_page(second)
        self.assertEqual(loaded.active['strokes'], [other])

    def test_looking_up_pages_never_overwrites_unsaved_flat_replacements(self):
        store = NotebookStore(self.path)
        store.active['strokes'] = [stroke()]
        store.active['texts'] = [text()]
        store.active['paper'] = 'grid'
        store.ensure_pages(store.active)
        _ = store.active_page
        self.assertEqual(store.active['strokes'], [stroke()])
        self.assertEqual(store.active['texts'], [text()])
        store.save()
        self.assertEqual(store.active_page['strokes'], [stroke()])
        self.assertEqual(store.active_page['texts'], [text()])
        self.assertEqual(store.active_page['paper'], 'grid')

    def test_every_page_is_validated_before_any_malformed_file_can_be_replaced(self):
        store = NotebookStore(self.path)
        store.new_page()
        store.save()
        payload = json.loads(self.path.read_text())
        for change in [lambda p: p.update(strokes=[{'unexpected': 'field'}]),
                       lambda p: p.update(strokes=[dict(stroke(), points=[[float('nan'), .2, .4]])]),
                       lambda p: p.update(texts=[dict(text(), norm_x=4)]),
                       lambda p: p.update(aspect=0), lambda p: p.update(paper='invalid')]:
            candidate = deepcopy(payload)
            # Corrupt the inactive page, not the page mirrored at note level.
            change(candidate['notes'][0]['pages'][0])
            data = json.dumps(candidate)
            self.path.write_text(data)
            with self.subTest(change=change), self.assertRaises(ValueError):
                NotebookStore(self.path)
            self.assertEqual(self.path.read_text(), data)

    def test_page_data_wins_over_stale_flat_mirror_when_loading(self):
        store = NotebookStore(self.path)
        store.active['strokes'] = [stroke()]
        store.save()
        payload = json.loads(self.path.read_text())
        payload['notes'][0]['strokes'] = []
        self.path.write_text(json.dumps(payload))
        loaded = NotebookStore(self.path)
        self.assertEqual(loaded.active['strokes'], [stroke()])


class NotebookPageCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'notes.json'
        self.host = PageHost(self.path)

    def test_add_select_and_status_keep_notebook_identity_and_change_page_identity(self):
        label_updates = []
        self.host._update_page_label = lambda: label_updates.append(self.host.store.active_page['id'])
        notebook = self.host.store.active_id
        first = self.host.store.active_page['id']
        self.host.draw()
        self.host.controller.sketchbook_texts = [NoteText(**text())]
        self.host.store.active.update(paper='grid', aspect=16/9)
        self.assertTrue(self.host.command('add'))
        second = self.host.store.active_page['id']
        self.assertNotEqual(first, second)
        self.assertEqual(self.host.store.active_id, notebook)
        self.assertEqual(self.host.controller.serialized_ink(), [])
        self.assertEqual(self.host.controller.serialized_texts(), [])
        self.assertEqual(self.host.canvas.paper, 'grid')
        self.assertEqual(self.host.canvas.aspect, 16/9)
        self.assertEqual(self.host._document_id, second)
        status = self.host._get_web_status()
        self.assertEqual(status['documentId'], second)
        self.assertEqual(status['notebookId'], notebook)
        self.assertEqual(status['pageId'], second)
        self.assertEqual((status['currentPage'], status['totalPages']), (1, 2))
        self.assertEqual([p['strokeCount'] for p in status['pages']], [1, 0])
        self.assertEqual([p['textCount'] for p in status['pages']], [1, 0])
        self.assertTrue(self.host.command('select', pageId=first))
        self.assertEqual(len(self.host.controller.sketchbook_strokes), 1)
        self.assertEqual(self.host.controller.sketchbook_texts[0].id, 'annotation-1')
        self.assertEqual(self.host._get_web_status()['currentPage'], 0)
        self.assertEqual(self.host.controller.undo_stack, [])
        self.assertEqual(label_updates, [second, first])
        self.assertEqual([e['type'] for e in self.host.events[-2:]], ['note_page_result', 'state_sync'])

    def test_view_only_switch_keeps_updated_timestamp_and_same_page_keeps_undo(self):
        self.host.draw()
        first = self.host.store.active_page['id']
        self.assertTrue(self.host.command('add'))
        timestamp = self.host.store.active['updatedAt']
        with patch('beamerplus.NotebookLibrary._now', return_value='2099-01-01T00:00:00.000Z'):
            self.assertTrue(self.host.command('select', pageId=first))
        self.assertEqual(self.host.store.active['updatedAt'], timestamp)
        self.host.draw()
        history = deepcopy(self.host.controller.undo_stack)
        revision = self.host.controller.ink_revision
        self.assertTrue(self.host.command('select', pageId=first))
        self.assertEqual(self.host.controller.undo_stack, history)
        self.assertEqual(self.host.controller.ink_revision, revision)

    def test_failed_initial_save_cannot_add_or_switch_and_finishes_pending_pen_safely(self):
        first = self.host.store.active_page['id']
        second = self.host.store.new_page()['id']
        self.host.store.select_page(first)
        self.host.draw(finish=False)
        self.host.legacy_failure = True
        for action, data in [('add', {}), ('select', {'pageId': second})]:
            with self.subTest(action=action):
                self.assertFalse(self.host.command(action, **data))
                self.assertEqual(self.host.store.active_page['id'], first)
                self.assertEqual(len(self.host.store.active['pages']), 2)
                self.assertEqual(len(self.host.controller.sketchbook_strokes), 1)
                self.assertIsNone(self.host.controller.current_stroke)

    def test_failed_candidate_write_preserves_old_page_controller_and_undo(self):
        self.host.draw()
        first = self.host.store.active_page['id']
        second = self.host.store.new_page()['id']
        self.host.store.select_page(first)
        for action, data in [('add', {}), ('select', {'pageId': second})]:
            history = deepcopy(self.host.controller.undo_stack)
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
            self.assertEqual(self.host.store.active_page['id'], first)
            self.assertEqual(self.host._document_id, first)
            self.assertEqual(len(self.host.store.active['pages']), 2)
            self.assertEqual(len(self.host.controller.sketchbook_strokes), 1)
            self.assertEqual(self.host.controller.undo_stack, history)
            self.assertEqual(json.loads(self.path.read_text())['notes'][0]['activePageId'], first)

    def test_stale_page_ink_end_and_undo_are_dropped_without_mutating_input(self):
        first = self.host.store.active_page['id']
        self.assertTrue(self.host.command('add'))
        current = self.host.store.active_page['id']
        self.host.draw(finish=False)
        active_stroke = self.host.controller.current_stroke
        for kind in ('stroke_start', 'stroke_move', 'stroke_end', 'erase_start', 'erase', 'erase_end',
                     'line_update', 'undo', 'redo', 'clear'):
            data = {'type': kind, 'documentId': first, 'normX': .8, 'normY': .6}
            original = deepcopy(data)
            self.assertFalse(self.host._on_page_ink_command(data))
            self.assertEqual(data, original)
        self.assertEqual(self.host.routed, [])
        self.assertIs(self.host.controller.current_stroke, active_stroke)
        data = {'type': 'stroke_move', 'documentId': current, 'normX': .4, 'normY': .5, 'page_id': current}
        original = deepcopy(data)
        self.assertTrue(self.host._on_page_ink_command(data))
        self.assertEqual(data, original)
        self.assertEqual(self.host.routed, [{key: value for key, value in data.items() if key != 'documentId'}])

    def test_invalid_page_request_does_not_interrupt_pen_and_other_commands_forward(self):
        self.host.draw(finish=False)
        active_stroke = self.host.controller.current_stroke
        for data in [dict(type='note_page', action='select', pageId='missing'),
                     dict(type='note_page', action='add', documentId='stale'),
                     dict(type='note_page', action='add', requestId='invalid/id')]:
            self.assertFalse(self.host._on_notebook_command(data))
            self.assertIs(self.host.controller.current_stroke, active_stroke)
        self.assertEqual(self.host.finish_calls, 0)
        self.host._on_notebook_command({'type': 'unrelated-command'})
        self.assertEqual(self.host.forwarded, [{'type': 'unrelated-command'}])


if __name__ == '__main__':
    unittest.main()
