"""Actual NotebookWindow integration for independent notebook pages."""

import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pymupdf
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from beamerplus.NotebookWindow import NotebookWindow


def canonical(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


class NotebookPageWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'pages.json'
        for target in ('beamerplus.WebServer.WebServer.start', 'beamerplus.WebServer.WebServer.stop',
                       'beamerplus.NotebookWindow.NotebookBridge'):
            mocked = patch(target, return_value=None)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.windows = []
        self.addCleanup(self._dispose_windows)
        self.events, self.replies = [], []
        self.client = object()
        self.window = self._new_window()

    def _new_window(self):
        window = NotebookWindow(store_path=self.path,
                                mcp_connection_file=Path(self.directory.name) / 'unused-mcp.json')
        window.web_server.broadcast = self.events.append
        window.web_server.reply_to = lambda client, message: self.replies.append((client, message))
        self.windows.append(window)
        return window

    def _close_window(self, window):
        if window in self.windows:
            window.close()
            window.save_timer.stop()
            window.erase_timer.stop()
            self.windows.remove(window)

    def _dispose_windows(self):
        for window in self.windows[:]:
            self._close_window(window)

    def page(self, action, **data):
        return self.window._on_notebook_command(dict(type='note_page', action=action,
                    requestId='page-window', documentId=self.window.store.active_page['id'], **data))

    def draw(self, second=False):
        controller = self.window.controller
        y = .6 if second else .2
        controller.begin_custom_stroke('#ef5350' if second else '#3478dc', .008, 1,
                                       .2, y, .5, brush='fountain')
        controller.add_stroke_point(.8, y + .1, .8)
        controller.end_stroke()

    def add_math(self, source=r'H(X\mid Y)=\frac{1}{2}'):
        metadata = self.window._handle_mcp_call('get_note_status', {})
        result = self.window._handle_mcp_call('add_note_text', dict(
            note_id=metadata['note_id'], page_id=metadata['page_id'], revision=metadata['revision'],
            text=source, norm_x=.12, norm_y=.4, size=18, color='#3478dc', format='latex'))
        self.assertTrue(result['saved'])
        return result['text_id']

    def two_pages(self, second_text=False):
        self.draw()
        first_text = self.add_math()
        first = self.window.store.active_page['id']
        self.assertTrue(self.page('add'))
        second = self.window.store.active_page['id']
        self.assertEqual(self.window.controller.serialized_ink(), [])
        self.assertEqual(self.window.controller.serialized_texts(), [])
        self.draw(second=True)
        if second_text:
            self.add_math(r'\sum_{i=1}^{n}i=\frac{n(n+1)}{2}')
        self.assertTrue(self.window.save_notebook())
        return first, second, first_text

    def file(self, action):
        self.window.web_server._handle_client_message(dict(type='note_file', action=action,
            requestId='page-window-file', documentId=self.window.store.active_page['id']), self.client)
        self.assertIs(self.replies[-1][0], self.client)
        return self.replies[-1][1]

    def test_ink_tex_blank_page_switch_save_and_actual_window_reopen_keep_both_pages(self):
        notebook = self.window.store.active_id
        first, second, text_id = self.two_pages()
        second_ink = canonical(self.window.controller.serialized_ink())
        self.assertTrue(self.page('select', pageId=first))
        first_ink = canonical(self.window.controller.serialized_ink())
        self.assertEqual(len(first_ink), 1)
        self.assertEqual(first_ink[0]['color'], '#3478dc')
        self.assertEqual(self.window.controller.sketchbook_texts[0].id, text_id)
        self.assertEqual(self.window.controller.sketchbook_texts[0].format, 'latex')
        self.assertIn(r'\frac', self.window.controller.sketchbook_texts[0].text)
        self.assertEqual(self.window.page_label.text(), '1 / 2 ページ')
        self.assertTrue(self.window.save_notebook())
        self._close_window(self.window)
        self.window = self._new_window()
        self.assertEqual(self.window.store.active_id, notebook)
        self.assertEqual(self.window.store.active_page['id'], first)
        self.assertEqual(canonical(self.window.controller.serialized_ink()), first_ink)
        self.assertEqual(self.window.controller.sketchbook_texts[0].id, text_id)
        self.assertTrue(self.page('select', pageId=second))
        self.assertEqual(canonical(self.window.controller.serialized_ink()), second_ink)
        self.assertEqual(self.window.controller.serialized_texts(), [])
        self.assertEqual(self.window._get_web_status()['totalPages'], 2)
        self.assertEqual(len(json.loads(self.path.read_text())['notes'][0]['pages']), 2)

    def test_mcp_page_metadata_and_revision_block_old_page_write(self):
        self.draw()
        first = self.window._handle_mcp_call('get_note_status', {})
        self.assertEqual(first['page_count'], 1)
        self.assertEqual(first['page_index'], 0)
        self.assertTrue(self.page('add'))
        second = self.window._handle_mcp_call('get_note_status', {})
        self.assertEqual(second['note_id'], first['note_id'])
        self.assertNotEqual(second['page_id'], first['page_id'])
        self.assertNotEqual(second['revision'], first['revision'])
        self.assertEqual((second['page_count'], second['page_index']), (2, 1))
        before = deepcopy(self.window.controller.serialized_texts())
        with self.assertRaisesRegex(ValueError, '更新'):
            self.window._handle_mcp_call('add_note_text', dict(note_id=first['note_id'],
                page_id=first['page_id'], revision=first['revision'], text='古いページへの書込み',
                norm_x=.1, norm_y=.1, size=18, color='#3478dc'))
        self.assertEqual(self.window.controller.serialized_texts(), before)
        self.add_math()
        self.assertEqual(len(self.window.controller.sketchbook_texts), 1)

    def test_notebook_duplicate_preserves_all_pages_and_renews_page_and_text_ids(self):
        self.two_pages(second_text=True)
        source = deepcopy(self.window.store.active)
        self.assertTrue(self.window._on_notebook_command(dict(type='note_library', action='duplicate',
                         id=source['id'], requestId='duplicate-all-pages')))
        clone = self.window.store.active
        self.assertNotEqual(clone['id'], source['id'])
        self.assertEqual(len(clone['pages']), 2)
        self.assertEqual(clone['activePageId'], clone['pages'][1]['id'])
        old_page_ids = {page['id'] for page in source['pages']}
        self.assertFalse(old_page_ids & {page['id'] for page in clone['pages']})
        old_text_ids = {item['id'] for page in source['pages'] for item in page['texts']}
        for before, after in zip(source['pages'], clone['pages']):
            self.assertEqual(canonical(before['strokes']), canonical(after['strokes']))
            self.assertEqual(before['paper'], after['paper'])
            self.assertEqual(before['aspect'], after['aspect'])
            self.assertEqual(len(before['texts']), len(after['texts']))
            for old, new in zip(before['texts'], after['texts']):
                self.assertNotIn(new['id'], old_text_ids)
                self.assertEqual({k: v for k, v in old.items() if k != 'id'},
                                 {k: v for k, v in new.items() if k != 'id'})
        self.assertEqual(self.window._document_id, clone['activePageId'])
        self.assertEqual(self.window.page_label.text(), '2 / 2 ページ')

    def test_pdf_contains_all_page_aspects_and_png_contains_current_page_only(self):
        first, second, _ = self.two_pages()
        self.window.store.active.update(aspect=.75, paper='ruled')
        self.window.canvas.aspect = .75
        self.window.canvas.paper = 'ruled'
        self.assertTrue(self.window.save_notebook())
        before = canonical(self.window.controller.serialized_ink())
        revision = self.window.controller.ink_revision
        pdf = self.file('pdf')
        self.assertTrue(pdf['ok'], pdf.get('message'))
        with pymupdf.open(stream=base64.b64decode(pdf['data']), filetype='pdf') as document:
            self.assertEqual(document.page_count, 2)
            for page, aspect in zip(document, (4 / 3, .75)):
                self.assertAlmostEqual(page.rect.width / page.rect.height, aspect, delta=.003)
            for index, y, color in ((0, .25, (52, 120, 220)), (1, .65, (239, 83, 80))):
                raster = document[index].get_pixmap()
                actual = raster.pixel(round(raster.width * .5), round(raster.height * y))[:3]
                self.assertTrue(all(abs(a - b) < 20 for a, b in zip(actual, color)), (index, actual))
        png = self.file('png')
        self.assertTrue(png['ok'], png.get('message'))
        self.assertIn('ページ2.png', png['filename'])
        image = QImage.fromData(base64.b64decode(png['data']))
        self.assertAlmostEqual(image.width() / image.height(), .75, delta=.002)
        self.assertEqual(image.pixelColor(image.width() // 2, round(image.height() * .65)).name(), '#ef5350')
        self.assertEqual(self.window.store.active_page['id'], second)
        self.assertEqual(self.window._document_id, second)
        self.assertEqual(canonical(self.window.controller.serialized_ink()), before)
        self.assertEqual(self.window.controller.ink_revision, revision)
        self.assertFalse(any(event.get('type') == 'note_file_result' for event in self.events))

    def test_failed_initial_save_blocks_page_add_and_select_without_touching_undo(self):
        first, second, _ = self.two_pages()
        for action, extra in (('add', {}), ('select', {'pageId': first})):
            previous = canonical(self.window.store.notes)
            ink = canonical(self.window.controller.serialized_ink())
            history = deepcopy(self.window.controller.undo_stack)
            revision = self.window.controller.ink_revision
            with self.subTest(action=action), patch.object(self.window, '_save_notebook_legacy', return_value=False):
                self.assertFalse(self.page(action, **extra))
            self.assertEqual(canonical(self.window.store.notes), previous)
            self.assertEqual(self.window.store.active_page['id'], second)
            self.assertEqual(self.window._document_id, second)
            self.assertEqual(canonical(self.window.controller.serialized_ink()), ink)
            self.assertEqual(self.window.controller.undo_stack, history)
            self.assertEqual(self.window.controller.ink_revision, revision)

    def test_failed_candidate_page_save_rolls_back_before_controller_load(self):
        first, second, _ = self.two_pages()
        for action, extra in (('add', {}), ('select', {'pageId': first})):
            previous = canonical(self.window.store.notes)
            ink = canonical(self.window.controller.serialized_ink())
            history = deepcopy(self.window.controller.undo_stack)
            real_save = self.window.store.save
            calls = 0

            def fail_candidate():
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('simulated candidate write failure')
                return real_save()

            with self.subTest(action=action), patch.object(self.window.store, 'save', side_effect=fail_candidate):
                self.assertFalse(self.page(action, **extra))
            self.assertEqual(canonical(self.window.store.notes), previous)
            self.assertEqual(self.window.store.active_page['id'], second)
            self.assertEqual(self.window._document_id, second)
            self.assertEqual(canonical(self.window.controller.serialized_ink()), ink)
            self.assertEqual(self.window.controller.undo_stack, history)

    def test_stale_page_ink_messages_cannot_stop_or_change_current_page_stroke(self):
        first, second, _ = self.two_pages()
        self.window.web_server._handle_client_message(dict(type='stroke_start', documentId=second,
            tool='pen', color='#202124', widthRatio=.004, opacity=1, normX=.1, normY=.8, pressure=.5))
        current = self.window.controller.current_stroke
        self.assertIsNotNone(current)
        before = canonical(self.window.controller.serialized_ink())
        pending = deepcopy(self.window.controller.pending_edit)
        revision = self.window.controller.ink_revision
        for kind in ('stroke_move', 'stroke_end', 'line_update', 'erase_start', 'erase', 'erase_end',
                     'clear', 'undo', 'redo'):
            self.window.web_server._handle_client_message(dict(type=kind, documentId=first,
                normX=.9, normY=.9, mode='stroke', size=70, pressure=1))
            self.assertIs(self.window.controller.current_stroke, current, kind)
            self.assertEqual(canonical(self.window.controller.serialized_ink()), before, kind)
            self.assertEqual(self.window.controller.pending_edit, pending, kind)
            self.assertEqual(self.window.controller.ink_revision, revision, kind)
            self.assertFalse(self.window._web_erase_active)
        self.assertFalse(self.window._on_notebook_command(dict(type='note_page', action='add',
                          documentId=first, requestId='stale-page-add')))
        self.assertIs(self.window.controller.current_stroke, current)
        self.window.web_server._handle_client_message(dict(type='stroke_move', documentId=second,
            normX=.8, normY=.85, pressure=.8))
        self.window.web_server._handle_client_message(dict(type='stroke_end', documentId=second))
        self.assertIsNone(self.window.controller.current_stroke)
        self.assertEqual(len(self.window.controller.sketchbook_strokes), 2)


if __name__ == '__main__':
    unittest.main()
