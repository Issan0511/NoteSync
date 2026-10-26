import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from beamerplus.NotebookModel import NotebookController, NotebookStore


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.controller = NotebookController()

    def stroke(self, brush='pen'):
        self.controller.begin_custom_stroke('#202124', .005, .8, .2, .2, .4, brush=brush)
        self.controller.add_stroke_point(.8, .2, .7)
        self.controller.end_stroke()

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
