from dataclasses import FrozenInstanceError
import math
import sys
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from beamerplus import NotebookMath as notebook_math
from beamerplus.NotebookMath import MathSvg, render_math_svg


ENTROPY = (r'H(X\mid Y)=-\sum_{y\in\mathcal{Y}}p(y)'
           r'\sum_{x\in\mathcal{X}}p(x\mid y)\log_2p(x\mid y)')
ALIGNED = (r'\begin{aligned}H(X,Y)&=H(Y)+H(X\mid Y)\\'
           r'I(X;Y)&=H(X)-H(X\mid Y)\end{aligned}')
FORMULAS = (ENTROPY, r'\frac{a+b}{c+d}', r'\sum_{i=1}^{n} i^2',
            r'\int_0^1 x^2\,dx', r'\begin{pmatrix}a&b\\c&d\end{pmatrix}', ALIGNED)


class NotebookMathTests(unittest.TestCase):
    def test_common_tex_including_entropy_integral_matrix_and_aligned_renders_in_qt(self):
        for source in FORMULAS:
            for inline in (True, False):
                with self.subTest(source=source, inline=inline):
                    result = render_math_svg(source, size=32, inline=inline)
                    self.assertIsInstance(result, MathSvg)
                    self.assertGreater(result.width, 0)
                    self.assertGreater(result.height, 0)
                    renderer = QSvgRenderer(QByteArray(result.svg.encode('utf-8')))
                    self.assertTrue(renderer.isValid())
                    image = QImage(math.ceil(result.width * 2), math.ceil(result.height * 2),
                                   QImage.Format.Format_ARGB32)
                    image.fill(QColor('#ffffff'))
                    painter = QPainter(image)
                    renderer.render(painter, QRectF(0, 0, image.width(), image.height()))
                    painter.end()
                    pixels = [image.pixelColor(x, y).name()
                              for y in range(0, image.height(), 2)
                              for x in range(0, image.width(), 2)]
                    self.assertGreater(sum(pixel != '#ffffff' for pixel in pixels), 10)
                    self.assertIn('#3478dc', pixels)

    def test_baseline_comes_from_svg_coordinate_origin_instead_of_font_height_guess(self):
        for source in (r'x_i^2', r'\frac{a}{b}', r'\int_0^1 f(x)\,dx', ALIGNED):
            result = render_math_svg(source, size=32, inline=True)
            root = ET.fromstring(result.svg)
            viewbox = [float(value) for value in root.get('viewBox').split()]
            self.assertEqual(result.baseline, -viewbox[1])
            self.assertEqual(result.width, viewbox[2])
            self.assertEqual(result.height, viewbox[3])
            self.assertGreater(result.baseline, 0)
            self.assertLess(result.baseline, result.height)
        simple = render_math_svg('x', size=32)
        fraction = render_math_svg(r'\frac{x}{y}', size=32)
        self.assertGreater(fraction.height, simple.height)
        self.assertGreater(fraction.baseline, simple.baseline)

    def test_svg_is_self_contained_paths_without_fonts_links_or_executable_elements(self):
        for source in FORMULAS:
            result = render_math_svg(source, color='#A13050', size=32)
            root = ET.fromstring(result.svg)
            for element in root.iter():
                tag = element.tag.rsplit('}', 1)[-1]
                self.assertIn(tag, ('svg', 'g', 'path', 'rect', 'line', 'polyline', 'polygon', 'circle', 'ellipse'))
                for attribute in element.attrib:
                    self.assertNotIn(attribute.lower(), ('href', 'style', 'src', 'onclick', 'onload'))
                if element.get('fill') not in (None, 'none'):
                    self.assertEqual(element.get('fill'), '#a13050')
            self.assertNotIn('<text', result.svg)
            self.assertNotIn('<use', result.svg)
            self.assertNotIn('xlink', result.svg)

    def test_result_is_immutable_and_repeated_render_uses_bounded_cache(self):
        source = r'\frac{cache_x}{cache_y}'
        first = render_math_svg(source, size=32)
        second = render_math_svg(source, size=32)
        self.assertIs(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.width = 1
        self.assertLessEqual(notebook_math._render.cache_info().currsize, 64)

    def test_render_restores_global_svg_compatibility_and_numbering_options(self):
        import ziamath
        previous = (ziamath.config.svg2, ziamath.config.precision, ziamath.config.numbering.autonumber)
        try:
            ziamath.config.svg2 = True
            ziamath.config.precision = 5
            ziamath.config.numbering.autonumber = True
            result = render_math_svg(r'\frac{restore_a}{restore_b}', size=31)
            self.assertNotIn('<use', result.svg)
            self.assertEqual((ziamath.config.svg2, ziamath.config.precision,
                              ziamath.config.numbering.autonumber), (True, 5, True))
        finally:
            ziamath.config.svg2, ziamath.config.precision, ziamath.config.numbering.autonumber = previous

    def test_escaped_literal_braces_and_percent_are_not_mistaken_for_grouping(self):
        self.assertTrue(QSvgRenderer(QByteArray(render_math_svg(r'\{x\}\quad 50\%').svg.encode())).isValid())

    def test_forbidden_resources_macros_and_custom_dimensions_are_rejected(self):
        sources = (r'\input{/tmp/private}', r'\includegraphics{https://example.com/x}',
                   r'\write18{touch /tmp/math}', r'\href{https://example.com}{x}',
                   r'\newcommand{\a}{\a\a}\a', r'\def\a{\a}\a',
                   r'\style{background:url(https://example.com)}{x}',
                   r'\color{red}{x}', r'\rule{999999999pt}{999999999pt}',
                   r'\begin{matrix}x\\[999999999pt]y\end{matrix}')
        for source in sources:
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, '[ぁ-んァ-ン一-龯]'):
                render_math_svg(source)

    def test_unknown_commands_and_bad_syntax_are_actionable_value_errors(self):
        for source in (r'\madeUpCommand{x}', r'\frac{', r'x}', r'\frac',
                       r'\begin{aligned}x&=1\end{matrix}', r'\begin{document}x\end{document}',
                       '', ' ', None, 'x\x00y', 'x\ud800y'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, '[ぁ-んァ-ン一-龯]'):
                render_math_svg(source)

    def test_source_nesting_and_table_budgets_reject_before_backend_render(self):
        sources = ('x' * 2001, '{' * 33 + 'x' + '}' * 33,
                   r'\begin{matrix}' + r'x\\' * 64 + r'y\end{matrix}',
                   r'\begin{matrix}' + 'x&' * 256 + r'y\end{matrix}')
        with patch.object(notebook_math, '_backend', side_effect=AssertionError('backend should not be reached')):
            for source in sources:
                with self.subTest(source=source[:50]), self.assertRaises(ValueError):
                    render_math_svg(source)

    def test_mathml_and_svg_complexity_budgets_are_enforced(self):
        source = r'\frac{budget_u}{budget_v}'
        with patch.object(notebook_math, 'MAX_MATHML_NODES', 2), self.assertRaises(ValueError):
            render_math_svg(source)
        with patch.object(notebook_math, 'MAX_SVG_BYTES', 10), self.assertRaises(ValueError):
            render_math_svg(r'\frac{svg_budget_u}{svg_budget_v}')

    def test_unsafe_svg_nodes_and_attributes_are_rejected(self):
        base = '<svg width="10" height="10" viewBox="0 -5 10 10"><path d="M0 0L1 1" fill="#3478dc" />{}</svg>'
        for payload in ('<image href="https://example.com" />', '<script>alert(1)</script>',
                        '<path d="M0 0L1 1" onclick="alert(1)" />'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                notebook_math._safe_svg(ET.fromstring(base.format(payload)))

    def test_size_color_and_display_arguments_are_bounded(self):
        for arguments in ({'size': True}, {'size': 0}, {'size': 97}, {'size': float('nan')},
                          {'size': 10 ** 1000}, {'color': 'url(https://example.com)'},
                          {'color': '#fff'}, {'inline': 'yes'}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                render_math_svg('x', **arguments)

    def test_absent_renderer_has_clear_error_without_breaking_module_import(self):
        notebook_math._backend.cache_clear()
        try:
            with patch.dict(sys.modules, {'ziamath': None}), self.assertRaisesRegex(ValueError, 'インストール'):
                render_math_svg('missing_dependency_xyz')
        finally:
            notebook_math._backend.cache_clear()


if __name__ == '__main__':
    unittest.main()
