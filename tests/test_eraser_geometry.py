"""A fixed-size eraser circle touches the visible ink edge, including pressure."""

import math
from types import SimpleNamespace
import unittest

from PySide6.QtCore import QRectF

from notesync.InkModel import Stroke, stroke_intersects_circle, clip_stroke_by_circle
from notesync.NotebookInput import NotebookInputMixin
from notesync.NotebookModel import NotebookController


class EraserGeometryTests(unittest.TestCase):
    def line(self, brush='pen', pressure=1):
        return Stroke('#202124', .02, 1, [(.2, .5, pressure), (.8, .5, pressure)], brush)

    def test_circle_touches_outer_ink_before_reaching_centerline(self):
        stroke = self.line()
        for aspect in (.75, 4/3):
            half_width = .01 * min(1, aspect)
            y = .5 + .02 + half_width
            self.assertTrue(stroke_intersects_circle(stroke, (.5, y), .02, aspect))
            self.assertFalse(stroke_intersects_circle(stroke, (.5, y + .00001), .02, aspect))

    def test_pressure_controls_the_fountain_ink_edge(self):
        for pressure in (0, .4, 1):
            stroke = self.line('fountain', pressure)
            y = .5 + .02 + .01 * (.35 + .9 * pressure)
            self.assertTrue(stroke_intersects_circle(stroke, (.5, y), .02))
            self.assertFalse(stroke_intersects_circle(stroke, (.5, y + .00001), .02))

    def test_dots_and_round_caps_include_visible_width_at_tangency(self):
        dot = Stroke(width_ratio=.02, points=[(.5, .5, 1)])
        self.assertTrue(stroke_intersects_circle(dot, (.53, .5), .02))
        self.assertFalse(stroke_intersects_circle(dot, (.53001, .5), .02))
        self.assertTrue(stroke_intersects_circle(self.line(), (.83, .5), .02))

    def test_highlighter_flat_cap_does_not_extend_past_visible_endpoint(self):
        stroke = self.line('highlighter')
        self.assertTrue(stroke_intersects_circle(stroke, (.82, .5), .02))
        self.assertFalse(stroke_intersects_circle(stroke, (.82001, .5), .02))
        self.assertTrue(stroke_intersects_circle(stroke, (.5, .53), .02))

    def test_partial_erase_cuts_ink_when_only_its_edge_intersects(self):
        stroke = self.line()
        clipped = clip_stroke_by_circle(stroke, (.5, .525), .02)
        self.assertEqual(len(clipped), 2)
        self.assertLess(clipped[0].points[-1][0], .5)
        self.assertGreater(clipped[1].points[0][0], .5)
        self.assertTrue(all(s.brush == stroke.brush and s.width_ratio == stroke.width_ratio for s in clipped))

    def test_touching_ink_deletes_whole_stroke_as_one_undoable_edit(self):
        controller = NotebookController()
        controller.load_ink([vars(self.line('fountain', 1))])
        original = controller.serialized_ink()
        self.assertTrue(controller.erase_at_point(.5, .5325, .02, 1, 'stroke'))
        controller.finish_edit()
        self.assertEqual(controller.serialized_ink(), [])
        controller.undo()
        self.assertEqual(controller.serialized_ink(), original)

    def test_server_accepts_zoom_compensated_radius_without_reapplying_minimum(self):
        calls = []
        controller = SimpleNamespace(erase_at_point=lambda *args, **kwargs:calls.append((args, kwargs)))
        host = SimpleNamespace(controller=controller, drawing_view=SimpleNamespace(
            canvas=SimpleNamespace(_get_page_rect=lambda:QRectF(0, 0, 600, 800))))
        NotebookInputMixin._on_web_erase_requested(host, dict(normX=.5, normY=.5, mode='stroke', size=5, radius=.0016))
        self.assertEqual(calls[-1][1]['threshold'], .0016)
        self.assertEqual(calls[-1][1]['aspect_ratio'], .75)
        NotebookInputMixin._on_web_erase_requested(host, dict(normX=.5, normY=.5, mode='stroke', size=5))
        self.assertEqual(calls[-1][1]['threshold'], .008,'legacy clients keep their old radius')
        NotebookInputMixin._on_web_erase_requested(host, dict(size=70, radius=.7))
        self.assertEqual(calls[-1][1]['threshold'], .7,'a fixed-size circle can span a deeply zoomed-out page')
        before = len(calls)
        for radius in (None, True, '0.01', math.nan, math.inf, -1, 0, 9):
            NotebookInputMixin._on_web_erase_requested(host, dict(size=25, radius=radius))
        self.assertEqual(len(calls), before)


if __name__ == '__main__':
    unittest.main()
