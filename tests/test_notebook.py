import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from beamerplus.NotebookModel import InkEditConflict, NotebookController, NotebookStore
from beamerplus.NotebookWindow import NotebookWindow


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.controller = NotebookController()

    def stroke(self, brush='pen'):
        self.controller.begin_custom_stroke('#202124', .005, .8, .2, .2, .4, brush=brush)
        self.controller.add_stroke_point(.8, .2, .7)
        self.controller.end_stroke()

    def edit(self, action, indices=None, **kwargs):
        return self.controller.apply_ink_edit(dict(action=action, indices=[0] if indices is None else indices,
                                                  baseRevision=self.controller.ink_revision, **kwargs))

    def test_selection_transform_preserves_pressure_and_is_one_undo_step(self):
        self.stroke('fountain')
        original = self.controller.serialized_ink()
        history = len(self.controller.undo_stack)
        revision = self.controller.ink_revision
        self.assertEqual(self.edit('transform', matrix=[2, 0, 0, 2, -.1, .1], widthScale=1.5), [0])
        transformed = self.controller.serialized_ink()
        for actual, expected in zip(transformed[0]['points'], [(.3, .5, .4), (1.5, .5, .7)]):
            for coordinate, expected_coordinate in zip(actual, expected):
                self.assertAlmostEqual(coordinate, expected_coordinate)
        self.assertEqual(transformed[0]['width_ratio'], .0075)
        self.assertEqual(transformed[0]['brush'], 'fountain')
        self.assertEqual(len(self.controller.undo_stack), history + 1)
        self.assertGreater(self.controller.ink_revision, revision)
        self.controller.undo()
        self.assertEqual(self.controller.serialized_ink(), original)
        self.controller.redo()
        self.assertEqual(self.controller.serialized_ink(), transformed)

    def test_selection_delete_duplicate_paste_and_style_are_undoable(self):
        self.stroke()
        original = self.controller.serialized_ink()
        self.assertEqual(self.edit('duplicate'), [1])
        self.assertEqual(len(self.controller.sketchbook_strokes), 2)
        self.assertAlmostEqual(self.controller.sketchbook_strokes[1].points[0][0], .22)
        self.edit('style', [1], color='#0088aa', opacity=.4, widthRatio=.02)
        self.assertEqual(self.controller.sketchbook_strokes[1].color, '#0088aa')
        self.assertEqual(self.controller.sketchbook_strokes[1].opacity, .4)
        self.assertEqual(self.controller.sketchbook_strokes[1].width_ratio, .02)
        self.assertEqual(self.edit('delete', [0, 1]), [])
        self.assertEqual(self.controller.serialized_ink(), [])
        self.controller.undo()
        self.assertEqual(len(self.controller.sketchbook_strokes), 2)
        self.controller.undo()
        self.assertEqual(self.controller.sketchbook_strokes[1].color, '#202124')
        self.controller.undo()
        self.assertEqual(self.controller.serialized_ink(), original)
        self.assertEqual(self.edit('paste', [], strokes=original, matrix=[1, 0, 0, 1, .1, .2]), [1])
        self.assertEqual(self.controller.sketchbook_strokes[1].points[0], (.30000000000000004, .4, .4))
        self.controller.undo()
        self.assertEqual(self.controller.serialized_ink(), original)
        self.assertEqual(self.controller.redo_stack[-1][1].brush, 'pen')

    def test_invalid_selection_data_cannot_change_ink_or_history(self):
        self.stroke()
        original = self.controller.serialized_ink()
        history = len(self.controller.undo_stack)
        revision = self.controller.ink_revision
        invalid = [dict(action='delete', indices=[True]), dict(action='delete', indices=[1]),
                   dict(action='transform', matrix=[1, 0, 0, 1, float('nan'), 0]),
                   dict(action='transform', widthScale=100), dict(action='style', color='url(evil)'),
                   dict(action='style', opacity=float('inf')), dict(action='style'),
                   dict(action='paste', indices=[], strokes=[dict(original[0], points=[[.1, .2, float('nan')]])]),
                   dict(action='paste', indices=[], strokes=[dict(original[0], points=[[.1, .2, .5, 4]])])]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.controller.apply_ink_edit(dict({'baseRevision': revision, 'indices': [0]}, **payload))
            self.assertEqual(self.controller.serialized_ink(), original)
            self.assertEqual(len(self.controller.undo_stack), history)
            self.assertEqual(self.controller.ink_revision, revision)

    def test_revision_blocks_stale_selection_including_a_pen_in_progress(self):
        self.stroke()
        stale = self.controller.ink_revision
        self.controller.begin_custom_stroke('#202124', .005, .8, .1, .1)
        pending = self.controller.current_stroke
        with self.assertRaises(InkEditConflict):
            self.controller.apply_ink_edit(dict(action='delete', indices=[0], baseRevision=stale))
        self.assertIs(self.controller.current_stroke, pending)
        revision = self.controller.ink_revision
        self.controller.add_stroke_point(.2, .2)
        self.assertGreater(self.controller.ink_revision, revision)
        self.controller.end_stroke()
        self.edit('delete', [0])
        self.controller.undo()
        self.assertEqual(len(self.controller.sketchbook_strokes), 2)
        self.controller.undo()
        self.assertEqual(len(self.controller.sketchbook_strokes), 1)

    def test_window_rejects_wrong_document_and_acknowledges_after_full_ink(self):
        self.stroke()
        original = self.controller.serialized_ink()
        events = []
        host = SimpleNamespace(controller=self.controller, store=SimpleNamespace(active_id='current'),
                               web_server=SimpleNamespace(broadcast=events.append), _finish_erase=lambda: None)
        host._get_web_status = lambda: dict(documentId='current', inkRevision=self.controller.ink_revision,
                                            sketchbookStrokes=self.controller.serialized_ink())
        host._sync_web_strokes_updated = lambda index: events.append(dict(type='strokes_updated',
                                                                         strokes=self.controller.serialized_ink()))
        payload = dict(action='delete', indices=[0], baseRevision=self.controller.ink_revision, requestId='selection-1')
        NotebookWindow._on_ink_edit(host, dict(payload, documentId='old-note'))
        self.assertEqual(self.controller.serialized_ink(), original)
        self.assertEqual([event['type'] for event in events], ['note_error', 'state_sync', 'note_ink_edit_result'])
        self.assertFalse(events[-1]['ok'])
        events.clear()
        NotebookWindow._on_ink_edit(host, dict(payload, documentId='current'))
        self.assertEqual([event['type'] for event in events], ['strokes_updated', 'note_ink_edit_result'])
        self.assertTrue(events[-1]['ok'])
        self.assertEqual(events[-1]['requestId'], 'selection-1')
        self.assertEqual(events[-1]['indices'], [])
        self.assertEqual(events[0]['strokes'], [])

    def test_whole_stroke_eraser_can_undo_and_redo_as_one_gesture(self):
        self.stroke()
        self.stroke('fountain')
        original = self.controller.serialized_ink()
        self.controller.begin_edit()
        self.controller.erase_at_point(.4, .2, .02, 4/3, 'stroke')
        self.controller.erase_at_point(.6, .2, .02, 4/3, 'stroke')
        self.controller.finish_edit()
        self.assertEqual(self.controller.sketchbook_strokes, [])
        self.controller.undo()
        self.assertEqual(self.controller.serialized_ink(), original)
        self.controller.redo()
        self.assertEqual(self.controller.sketchbook_strokes, [])

    def test_partial_eraser_preserves_brush_and_undo_restores_original(self):
        self.stroke('fountain')
        original = self.controller.serialized_ink()
        self.controller.erase_at_point(.5, .2, .04, 4/3, 'partial')
        self.controller.finish_edit()
        self.assertEqual(len(self.controller.sketchbook_strokes), 2)
        self.assertTrue(all(s.brush == 'fountain' for s in self.controller.sketchbook_strokes))
        self.controller.undo()
        self.assertEqual(self.controller.serialized_ink(), original)

    def test_clear_is_undoable_and_new_ink_discards_redo(self):
        self.stroke()
        self.controller.clear_strokes()
        self.assertEqual(self.controller.sketchbook_strokes, [])
        self.controller.undo()
        self.assertEqual(len(self.controller.sketchbook_strokes), 1)
        self.controller.undo()
        self.stroke('pencil')
        self.controller.redo()
        self.assertEqual(len(self.controller.sketchbook_strokes), 1)
        self.assertEqual(self.controller.sketchbook_strokes[0].brush, 'pencil')

    def test_notebooks_reload_ink_titles_and_active_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'notes.json'
            store = NotebookStore(path)
            self.stroke('fountain')
            store.active['title'] = '応用代数学'
            store.active['strokes'] = self.controller.serialized_ink()
            first = store.active_id
            store.new_note('計算メモ')
            store.save()
            loaded = NotebookStore(path)
            self.assertEqual(loaded.active['title'], '計算メモ')
            loaded.active_id = first
            self.assertEqual(loaded.active['title'], '応用代数学')
            self.controller.load_ink(loaded.active['strokes'])
            self.assertEqual(self.controller.sketchbook_strokes[0].brush, 'fountain')
            self.assertEqual(self.controller.undo_stack, [])

    def test_invalid_saved_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'notes.json'
            original = '{"version":9,"notes":[]}'
            path.write_text(original)
            with self.assertRaises(ValueError):
                NotebookStore(path)
            self.assertEqual(path.read_text(), original)

    def test_legacy_ink_keeps_aspect_and_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotebookStore(Path(directory)/'notes.json')
            self.stroke()
            strokes = self.controller.serialized_ink()
            store.import_ink(strokes)
            self.assertEqual(store.active['aspect'], 16/9)
            store.new_note('新しい計算')
            active = store.active_id
            store.import_ink(strokes)
            self.assertEqual(len(store.notes), 2)
            self.assertEqual(store.active_id, active)

    def test_failed_atomic_write_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'notes.json'
            store = NotebookStore(path)
            store.save()
            previous = path.read_text()
            store.active['title'] = '変更後'
            with patch('beamerplus.NotebookModel.os.replace', side_effect=PermissionError):
                with self.assertRaises(PermissionError):
                    store.save()
            self.assertEqual(path.read_text(), previous)
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
