"""Vector annotation transforms share selection edits, history and persistence."""

from copy import deepcopy
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PIL import Image, ImageChops
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from notesync.InkModel import text_intersects_circle
from notesync.NotebookExports import create_notebook_backup, parse_notebook_backup
from notesync.NotebookModel import NotebookController, NotebookStore, InkEditConflict
from notesync.NotebookText import annotation_payload, paint_note_texts, prepare_text, text_bounds, transform_note_text
from notesync.NotebookWindow import NotebookWindow


class AnnotationSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = NotebookController()
        self.item = self.controller.add_note_text(dict(text=r'$\frac{1}{n}\sum_{i=1}^{n}x_i$',
                norm_x=.15, norm_y=.2, size=22), .75)
        self.controller.begin_custom_stroke('#202124', .004, 1, .1, .1)
        self.controller.add_stroke_point(.3, .2)
        self.controller.end_stroke()

    def edit(self, action='transform', **data):
        return self.controller.apply_ink_edit(dict(action=action, indices=[], textIds=[self.item.id],
            baseRevision=self.controller.ink_revision, **data), .75)

    def test_resize_preserves_tex_and_id_and_repeated_transforms_compose_without_reflow(self):
        original = deepcopy(self.item)
        old_svg = annotation_payload(original, .75)['renderedSvg']
        bounds = text_bounds(original, .75)
        self.assertEqual(self.edit(matrix=[2, 0, 0, 2, -.15, -.2], widthScale=2), [])
        item = self.controller.sketchbook_texts[0]
        after = text_bounds(item, .75)
        self.assertAlmostEqual(after['x'], bounds['x'])
        self.assertAlmostEqual(after['width'], bounds['width']*2)
        self.assertEqual((item.id, item.text, item.format, item.size),
                         (original.id, original.text, original.format, original.size))
        self.assertEqual(annotation_payload(item, .75)['renderedSvg'], old_svg)
        self.edit(matrix=[1, 0, 0, 1, .12, .08])
        item = self.controller.sketchbook_texts[0]
        self.assertAlmostEqual(text_bounds(item, .75)['x'], after['x']+.12)
        self.assertEqual(item.transform[:4], [2, 0, 0, 2])

    def test_mixed_ink_and_text_are_one_undo_step(self):
        before = (self.controller.serialized_ink(), self.controller.serialized_texts())
        history = len(self.controller.undo_stack)
        self.controller.apply_ink_edit(dict(action='transform', indices=[0], textIds=[self.item.id],
                baseRevision=self.controller.ink_revision, matrix=[1.5, 0, 0, 1.5, .05, .04], widthScale=1.5), .75)
        after = (self.controller.serialized_ink(), self.controller.serialized_texts())
        self.assertEqual(len(self.controller.undo_stack), history+1)
        self.assertNotEqual(before, after)
        self.controller.undo()
        self.assertEqual((self.controller.serialized_ink(), self.controller.serialized_texts()), before)
        self.controller.redo()
        self.assertEqual((self.controller.serialized_ink(), self.controller.serialized_texts()), after)

    def test_copy_paste_duplicate_delete_and_color_keep_editable_text_with_fresh_ids(self):
        self.edit('duplicate')
        duplicate = self.controller.sketchbook_texts[-1]
        self.assertNotEqual(duplicate.id, self.item.id)
        self.assertEqual(duplicate.text, self.item.text)
        self.assertEqual(self.controller._last_edited_text_ids, [duplicate.id])
        self.controller.apply_ink_edit(dict(action='paste', indices=[], textIds=[], strokes=[],
            texts=[asdict(duplicate)], baseRevision=self.controller.ink_revision, matrix=[1, 0, 0, 1, .1, .1]), .75)
        pasted = self.controller.sketchbook_texts[-1]
        self.assertNotIn(pasted.id, [self.item.id, duplicate.id])
        for actual, expected in zip(pasted.transform, [1, 0, 0, 1, .12, .12]):
            self.assertAlmostEqual(actual, expected)
        self.edit('style', color='#ef5350')
        self.assertEqual(self.controller.sketchbook_texts[0].color, '#ef5350')
        self.edit('delete')
        self.assertNotIn(self.item.id, [item.id for item in self.controller.sketchbook_texts])
        self.controller.undo()
        self.assertEqual(self.controller.sketchbook_texts[0].id, self.item.id)

    def test_rotation_bounds_and_eraser_use_transformed_position(self):
        bounds = text_bounds(self.item, .75)
        moved = transform_note_text(self.item, [1, 0, 0, 1, .45, .4], .75)
        self.assertFalse(text_intersects_circle(moved, (.16, .21), .001, .75))
        self.assertTrue(text_intersects_circle(moved, (.61, .61), .001, .75))
        angle = math.pi/2
        matrix = [math.cos(angle), math.sin(angle)*.75, -math.sin(angle)/.75, math.cos(angle), .8, 0]
        rotated = text_bounds(transform_note_text(self.item, matrix, .75), .75)
        self.assertAlmostEqual(rotated['width'], bounds['height']/.75)
        self.assertAlmostEqual(rotated['height'], bounds['width']*.75)

    def test_stale_or_invalid_text_requests_never_finish_pen_or_partially_change_ink(self):
        self.controller.begin_custom_stroke('#202124', .004, 1, .5, .5)
        active = self.controller.current_stroke
        before = (self.controller.serialized_ink(), self.controller.serialized_texts(), deepcopy(self.controller.undo_stack))
        for data in [dict(textIds=['missing']), dict(textIds=[True]), dict(matrix=[1,0,0,0,0,0]),
                     dict(matrix=[1,0,0,1,math.nan,0]), dict(matrix=[64,0,0,64,0,0])]:
            payload = dict(action='transform', indices=[0], textIds=[self.item.id],
                           baseRevision=self.controller.ink_revision, matrix=[1,0,0,1,0,0])
            payload.update(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.controller.apply_ink_edit(payload, .75)
            self.assertIs(self.controller.current_stroke, active)
            self.assertEqual((self.controller.serialized_ink(), self.controller.serialized_texts(), self.controller.undo_stack), before)
        with self.assertRaises(InkEditConflict):
            self.controller.apply_ink_edit(dict(action='delete', textIds=[self.item.id], baseRevision=-1), .75)

    def test_identity_transform_and_invalid_paste_do_not_create_history(self):
        history = len(self.controller.undo_stack)
        revision = self.controller.ink_revision
        self.edit(matrix=[1, 0, 0, 1, 0, 0])
        self.assertEqual(self.controller.ink_revision, revision)
        self.assertEqual(len(self.controller.undo_stack), history)
        with self.assertRaises(ValueError):
            self.controller.apply_ink_edit(dict(action='paste', indices=[], textIds=[], strokes=[],
                texts=[asdict(self.item), dict(text='bad')], baseRevision=revision), .75)
        self.assertEqual(len(self.controller.sketchbook_texts), 1)

    def test_save_reload_and_backup_keep_transform_without_rendered_svg(self):
        self.edit(matrix=[1.8, 0, 0, 1.8, .04, .03])
        with tempfile.TemporaryDirectory() as folder:
            store = NotebookStore(Path(folder)/'notes.json')
            store.active['texts'] = self.controller.serialized_texts()
            store.save()
            loaded = NotebookStore(store.path)
            self.assertEqual(loaded.active['texts'], self.controller.serialized_texts())
            backup = create_notebook_backup(loaded.notes)
            self.assertNotIn(b'renderedSvg', backup)
            restored = parse_notebook_backup(backup)['notes'][0]['texts'][0]
            self.assertEqual(restored['transform'], loaded.active['texts'][0]['transform'])
            self.assertEqual(restored['text'], self.item.text)

    def test_qt_renderer_scales_the_same_formula_about_the_page_origin(self):
        def render(item):
            image = QImage(1100, 1500, QImage.Format.Format_RGB32)
            image.fill('white')
            painter = QPainter(image)
            paint_note_texts(painter, [item], QRectF(50, 70, 1000, 1400))
            painter.end()
            pil = Image.frombytes('RGB', (image.width(),image.height()), bytes(image.bits()), 'raw', 'BGRX')
            return ImageChops.difference(pil, Image.new('RGB',pil.size,'white')).getbbox()
        original = render(self.item)
        transformed = render(transform_note_text(self.item, [1.5, 0, 0, 1.5, .1, .05], 1000/1400))
        expected = [50+(original[0]-50)*1.5+100,70+(original[1]-70)*1.5+70,
                    50+(original[2]-50)*1.5+100,70+(original[3]-70)*1.5+70]
        for actual, value in zip(transformed, expected):
            self.assertAlmostEqual(actual, value, delta=3)


class AnnotationSelectionWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_window_ack_contains_canonical_transformed_text_and_reopen_preserves_it(self):
        with tempfile.TemporaryDirectory() as folder, patch('notesync.WebServer.WebServer.start'), patch(
                'notesync.WebServer.WebServer.stop'), patch('notesync.NotebookWindow.NotebookBridge',return_value=None):
            path=Path(folder)/'notes.json'
            window=NotebookWindow(path)
            try:
                item=window.controller.add_note_text(dict(text=r'$x^2+y^2$',norm_x=.2,norm_y=.2,size=18),.75)
                events=[]
                window.web_server.broadcast=events.append
                window._on_ink_edit(dict(action='transform',indices=[],textIds=[item.id],
                    documentId=window._document_id,baseRevision=window.controller.ink_revision,
                    requestId='resize-text',matrix=[2,0,0,2,-.2,-.2],widthScale=2))
                result=next(event for event in events if event['type']=='note_ink_edit_result')
                self.assertTrue(result['ok'])
                self.assertEqual(result['textIds'],[item.id])
                self.assertIn('renderedSvg',result['texts'][0])
                self.assertEqual(result['texts'][0]['transform'],[2,0,0,2,-.2,-.2])
                self.assertAlmostEqual(result['texts'][0]['bounds']['x'],.2)
                self.assertTrue(window.save_notebook())
                self.assertEqual(NotebookStore(path).active['texts'][0]['transform'],[2,0,0,2,-.2,-.2])
            finally:
                window.close()


if __name__ == '__main__':
    unittest.main()
