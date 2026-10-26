from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from beamerplus.NotebookExports import create_notebook_backup, parse_notebook_backup
from beamerplus.NotebookText import annotation_payload, paint_note_texts, prepare_text, text_bounds
from beamerplus.NotebookWindow import NotebookWindow


class AnnotationMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def item(self, text, **options):
        return prepare_text(dict({'text': text, 'norm_x': .15, 'norm_y': .2}, **options), 4 / 3)

    def test_inline_japanese_and_tex_are_one_safe_renderable_block(self):
        item = self.item(r'条件付きエントロピー $H(X\mid Y)\leq H(X\mid Z)$ を示す。')
        payload = annotation_payload(item, 4 / 3)
        self.assertEqual(payload['text'], item.text)
        self.assertIn('条件付きエントロピー', payload['renderedSvg'])
        self.assertIn('path', payload['renderedSvg'])
        self.assertTrue(QSvgRenderer(QByteArray(payload['renderedSvg'].encode())).isValid())
        bounds = text_bounds(item, 4 / 3)
        self.assertAlmostEqual(bounds['width'], payload['renderedWidth'] * item.size * .0015 * 3 / 4)
        self.assertAlmostEqual(bounds['height'], payload['renderedHeight'] * item.size * .0015)
        literal = self.item('<script>alert(1)</script> $x^2$')
        self.assertNotIn('<script>', annotation_payload(literal, 4 / 3)['renderedSvg'])

    def test_explicit_latex_and_forced_literal_text_preserve_the_original_source(self):
        source = r'\frac{1}{n}\sum_{i=1}^{n}x_i'
        formula = self.item(source, format='latex')
        self.assertIn('renderedSvg', annotation_payload(formula, 4 / 3))
        self.assertEqual(formula.text, source)
        literal = self.item('$x^2$', format='text')
        self.assertNotIn('renderedSvg', annotation_payload(literal, 4 / 3))
        self.assertEqual(literal.text, '$x^2$')

    def test_matrix_aligned_and_display_delimiters_have_finite_bounds(self):
        for source in (r'\[\begin{pmatrix}1&2\\3&4\end{pmatrix}\]',
                       r'$$\begin{aligned}a&=b+c\\&=d\end{aligned}$$',
                       r'面積は \(\int_0^1 x^2\,dx\) です。'):
            with self.subTest(source=source):
                item = self.item(source)
                bounds = text_bounds(item, 4 / 3)
                self.assertGreater(bounds['width'], 0)
                self.assertLessEqual(bounds['x'] + bounds['width'], .98001)
                self.assertLessEqual(bounds['y'] + bounds['height'], .98)

    def test_formula_rejects_out_of_page_placement_before_mutating(self):
        with self.assertRaises(ValueError):
            self.item(r'\frac{a}{b}', format='latex', norm_y=.97)

    def test_backup_keeps_latex_source_and_format_without_cached_svg(self):
        item = self.item(r'\frac{a}{b}', format='latex')
        raw = create_notebook_backup([dict(id='math-note', title='数式', paper='plain', aspect=4/3,
                                          strokes=[], texts=[asdict(item)])], active_id='math-note')
        saved = json.loads(raw)['notes'][0]['texts'][0]
        self.assertEqual(saved['format'], 'latex')
        self.assertEqual(saved['text'], item.text)
        self.assertNotIn('renderedSvg', saved)
        imported = parse_notebook_backup(raw)['notes'][0]['texts'][0]
        self.assertEqual(imported['format'], 'latex')
        self.assertNotEqual(imported['id'], item.id)

    def test_the_shared_svg_is_visible_in_desktop_painting(self):
        image = QImage(800, 600, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        item = self.item(r'\frac{a+b}{c}', format='latex')
        painter = QPainter(image)
        paint_note_texts(painter, [item], QRectF(0, 0, 800, 600))
        painter.end()
        pixels = sum(image.pixelColor(x, y) != Qt.GlobalColor.white
                     for y in range(110, 240, 2) for x in range(100, 350, 2))
        self.assertGreater(pixels, 10)

    def test_mcp_write_and_initial_sync_contain_the_same_math_payload(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('beamerplus.WebServer.WebServer.start'), \
                patch('beamerplus.WebServer.WebServer.stop'), \
                patch('beamerplus.NotebookWindow.NotebookBridge', return_value=None):
            window = NotebookWindow(store_path=Path(directory) / 'notes.json')
            try:
                events = []
                window.web_server.broadcast = events.append
                original = window._handle_mcp_call('get_note_status', {})
                result = window._handle_mcp_call('add_note_text', dict(note_id=original['note_id'],
                    revision=original['revision'], text=r'\frac{a}{b}', format='latex', norm_x=.2, norm_y=.3))
                self.assertTrue(result['saved'])
                update = next(event for event in events if event['type'] == 'note_texts_updated')
                initial = window._get_web_status()['noteTexts']
                self.assertEqual(update['texts'], initial)
                self.assertIn('renderedSvg', initial[0])
                window.controller.undo()
                self.assertEqual(window._get_web_status()['noteTexts'], [])
                window.controller.redo()
                self.assertEqual(window._get_web_status()['noteTexts'], initial)
            finally:
                window.close()
