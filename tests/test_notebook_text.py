from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest

from notesync.NotebookModel import NotebookController, NotebookStore
from notesync.NotebookText import text_bounds


class NotebookTextTests(unittest.TestCase):
    def setUp(self):
        self.controller = NotebookController()

    def add_text(self, text='両辺を x で割る前に、x ≠ 0 を確かめよう。', **kwargs):
        return self.controller.add_note_text(dict(text=text, norm_x=.55, norm_y=.4, **kwargs))

    def stroke(self):
        self.controller.begin_custom_stroke('#202124', .005, 1, .1, .2)
        self.controller.add_stroke_point(.4, .2)
        self.controller.end_stroke()

    def test_mixed_handwriting_and_tutor_edits_share_undo_and_redo(self):
        self.stroke()
        ink = self.controller.serialized_ink()
        item = self.add_text()
        self.stroke()
        self.controller.undo()
        self.assertEqual(self.controller.serialized_ink(), ink)
        self.assertEqual(self.controller.sketchbook_texts, [item])
        self.controller.undo()
        self.assertEqual(self.controller.sketchbook_texts, [])
        self.assertEqual(self.controller.serialized_ink(), ink)
        self.controller.redo()
        self.assertEqual(self.controller.sketchbook_texts, [item])
        self.controller.clear_strokes()
        self.assertEqual(self.controller.sketchbook_strokes, [])
        self.assertEqual(self.controller.sketchbook_texts, [])
        self.controller.undo()
        self.assertEqual(self.controller.serialized_ink(), ink)
        self.assertEqual(self.controller.sketchbook_texts, [item])
        self.controller.remove_note_text(item.id)
        self.assertEqual(self.controller.serialized_ink(), ink)
        self.controller.undo()
        self.assertEqual(self.controller.sketchbook_texts, [item])

    def test_multiline_text_can_be_erased_on_its_last_line_and_restored(self):
        item = self.add_text('一段目\n二段目\n三段目')
        bounds = text_bounds(item, 4 / 3)
        self.controller.erase_at_point(item.norm_x + .01, item.norm_y + bounds['height'] * .85, .005, 4 / 3)
        self.controller.finish_edit()
        self.assertEqual(self.controller.sketchbook_texts, [])
        self.controller.undo()
        self.assertEqual(self.controller.sketchbook_texts, [item])

    def test_invalid_annotation_cannot_finish_pen_gesture_or_change_history(self):
        self.stroke()
        self.controller.begin_custom_stroke('#202124', .005, 1, .1, .2)
        current = self.controller.current_stroke
        history = len(self.controller.undo_stack)
        for payload in [dict(text=''), dict(norm_x=float('nan')), dict(norm_y=True), dict(size=999),
                        dict(color='url(evil)'), dict(norm_x=.98), dict(norm_y=.97), dict(text='a\x00b')]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.controller.add_note_text(dict({'text': '確認しよう', 'norm_x': .4, 'norm_y': .4}, **payload))
            self.assertIs(self.controller.current_stroke, current)
            self.assertEqual(len(self.controller.undo_stack), history)
            self.assertEqual(self.controller.sketchbook_texts, [])

    def test_text_identity_line_breaks_and_ink_survive_atomic_save_and_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotebookStore(Path(directory) / 'notes.json')
            # This fixture creates its annotation with the legacy landscape layout.
            store.active['aspect'] = 4 / 3
            self.stroke()
            item = self.add_text()
            self.assertIn('\n', item.text)
            store.active['strokes'] = self.controller.serialized_ink()
            store.active['texts'] = self.controller.serialized_texts()
            store.save()
            loaded = NotebookStore(store.path)
            self.assertEqual(loaded.active['texts'], [asdict(item)])
            self.controller.load_ink(loaded.active['strokes'], loaded.active['texts'])
            self.assertEqual(self.controller.sketchbook_texts, [item])
            self.assertEqual(self.controller.undo_stack, [])


if __name__ == '__main__':
    unittest.main()
