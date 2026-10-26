from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import pymupdf
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter

from beamerplus import NotebookExports as exports
from tests.test_notebook_exports import sample_note, TEXT_ANNOTATIONS_AVAILABLE


def paged_note(identifier='paged_note', with_text=False):
    note = sample_note(identifier)
    if not with_text:
        note['texts'] = []
    first = {'id': identifier, **{key: deepcopy(note[key]) for key in ('paper', 'aspect', 'strokes', 'texts')}}
    second = deepcopy(first)
    second.update(id=identifier + '_second', paper='ruled', aspect=.75)
    second['strokes'][0]['points'] = [[.7, .6, .2], [.8, .7, .9]]
    second['strokes'][0]['color'] = '#ef5350'
    if with_text:
        second['texts'][0]['text'] = '二枚目のページ'
    # Deliberately leave a stale first-page mirror: pages must remain canonical.
    note.update(pages=[first, second], activePageId=second['id'])
    return note


def without_ids(value):
    if isinstance(value, dict):
        return {key: without_ids(item) for key, item in value.items() if key not in ('id', 'activePageId')}
    if isinstance(value, list):
        return [without_ids(item) for item in value]
    return value


def image(width, height, color):
    result = QImage(width, height, QImage.Format.Format_ARGB32)
    result.fill(QColor(0, 0, 0, 0))
    painter = QPainter(result)
    painter.fillRect(QRect(width // 4, height // 4, width // 2, height // 2), QColor(color))
    painter.end()
    return result


class PageBackupTests(unittest.TestCase):
    def test_all_pages_roundtrip_and_active_mirror_and_ids_are_rebuilt(self):
        note = paged_note()
        previous = deepcopy(note)
        backup = exports.create_notebook_backup([note], active_id=note['id'])
        encoded = json.loads(backup)['notes'][0]
        self.assertEqual(len(encoded['pages']), 2)
        self.assertEqual(encoded['strokes'], encoded['pages'][1]['strokes'])
        self.assertEqual(encoded['paper'], 'ruled')
        self.assertEqual(encoded['aspect'], .75)
        restored = exports.parse_notebook_backup(backup, existing_notes=[note])
        imported = restored['notes'][0]
        self.assertEqual(restored['activeId'], imported['id'])
        self.assertEqual(imported['activePageId'], imported['pages'][1]['id'])
        self.assertEqual(without_ids(imported['pages']), without_ids(encoded['pages']))
        self.assertEqual(imported['strokes'], imported['pages'][1]['strokes'])
        source_ids = {note['id'], *(page['id'] for page in note['pages'])}
        fresh_ids = [imported['id'], *(page['id'] for page in imported['pages'])]
        self.assertEqual(len(set(fresh_ids)), 3)
        self.assertFalse(source_ids & set(fresh_ids))
        self.assertEqual(note, previous)

    @unittest.skipUnless(TEXT_ANNOTATIONS_AVAILABLE, 'Optional text annotations are not installed')
    def test_annotation_ids_are_fresh_on_every_page_and_active_text_mirror_matches(self):
        note = paged_note(with_text=True)
        note['pages'][1]['texts'][0]['format'] = 'text'
        backup = exports.create_notebook_backup([note])
        imported = exports.parse_notebook_backup(backup, existing_notes=[note])['notes'][0]
        self.assertEqual(len(imported['pages'][0]['texts']), 1)
        self.assertEqual(len(imported['pages'][1]['texts']), 1)
        identifiers = [item['id'] for page in imported['pages'] for item in page['texts']]
        self.assertEqual(len(set(identifiers)), 2)
        self.assertNotIn('text_original', identifiers)
        self.assertEqual(imported['texts'], imported['pages'][1]['texts'])
        self.assertEqual(imported['texts'][0]['format'], 'text')
        self.assertEqual(imported['pages'][0]['texts'][0]['text'], note['pages'][0]['texts'][0]['text'])
        self.assertEqual(imported['pages'][1]['texts'][0]['text'], '二枚目のページ')

    def test_legacy_flat_only_and_mixed_collection_backups_keep_all_ink(self):
        legacy = sample_note('legacy_note')
        legacy.pop('texts')
        paged = paged_note()
        backup = exports.create_notebook_backup([legacy, paged], active_id=legacy['id'])
        encoded = json.loads(backup)['notes']
        self.assertNotIn('pages', encoded[0])
        self.assertNotIn('activePageId', encoded[0])
        self.assertEqual(len(encoded[1]['pages']), 2)
        imported = exports.parse_notebook_backup(backup)['notes']
        self.assertNotIn('pages', imported[0])
        self.assertEqual(imported[0]['strokes'], legacy['strokes'])
        self.assertEqual(imported[1]['pages'][0]['strokes'], paged['pages'][0]['strokes'])
        self.assertEqual(imported[1]['pages'][1]['strokes'], paged['pages'][1]['strokes'])

    def test_invalid_later_page_rejects_entire_backup_without_mutation(self):
        note = paged_note()
        existing = [paged_note('existing')]
        previous = deepcopy(existing)
        for broken in ([], None, ['not-a-page']):
            candidate = deepcopy(note)
            candidate['pages'] = broken
            with self.subTest(pages=broken), self.assertRaises(ValueError):
                exports.parse_notebook_backup(json.dumps({'version': 1, 'notes': [candidate]}), existing_notes=existing)
        for modify in (lambda p: p.update(id='../private/path'),
                       lambda p: p.update(aspect=0),
                       lambda p: p['strokes'][0].update(points=[[1, 999, 1]])):
            candidate = deepcopy(note)
            modify(candidate['pages'][1])
            with self.subTest(modification=modify), self.assertRaises(ValueError):
                exports.parse_notebook_backup(json.dumps({'version': 1, 'notes': [candidate]}), existing_notes=existing)
        self.assertEqual(existing, previous)

    def test_active_page_reference_is_validated_and_missing_reference_defaults_to_first(self):
        note = paged_note()
        note['activePageId'] = 'not_present'
        with self.assertRaises(ValueError):
            exports.create_notebook_backup([note])
        del note['activePageId']
        restored = exports.parse_notebook_backup(exports.create_notebook_backup([note]))['notes'][0]
        self.assertEqual(restored['activePageId'], restored['pages'][0]['id'])
        self.assertEqual(restored['strokes'], restored['pages'][0]['strokes'])

    def test_point_and_page_limits_are_shared_across_pages_without_double_counting_mirror(self):
        note = paged_note()
        with patch.object(exports, 'MAX_POINTS', 4):
            self.assertEqual(len(json.loads(exports.create_notebook_backup([note]))['notes'][0]['pages']), 2)
        with patch.object(exports, 'MAX_POINTS', 3), self.assertRaises(ValueError):
            exports.create_notebook_backup([note])
        with patch.object(exports, 'MAX_PAGES', 1), self.assertRaises(ValueError):
            exports.create_notebook_backup([note])
        legacy = sample_note('legacy')
        legacy.pop('texts')
        with patch.object(exports, 'MAX_PAGES', 2), self.assertRaises(ValueError):
            exports.create_notebook_backup([note, legacy])

    @unittest.skipUnless(TEXT_ANNOTATIONS_AVAILABLE, 'Optional text annotations are not installed')
    def test_text_budget_is_shared_across_all_pages(self):
        note = paged_note(with_text=True)
        with patch.object(exports, 'MAX_TEXTS', 1), self.assertRaises(ValueError):
            exports.create_notebook_backup([note])

    def test_page_private_fields_are_not_exported(self):
        note = paged_note()
        note['pages'][0].update(api_key='page-secret', path='/private/page')
        output = exports.create_notebook_backup([note]).decode()
        self.assertNotIn('page-secret', output)
        self.assertNotIn('/private/page', output)


class MultipagePdfTests(unittest.TestCase):
    def test_generator_streams_different_aspects_colors_and_keeps_every_page(self):
        specs = [(400, 300, '#3478dc'), (300, 500, '#ef5350'), (640, 360, '#42b68e')]
        configured = []
        original = exports._pdf_page_size

        def configure(writer, rendered):
            configured.append((rendered.width(), rendered.height()))
            return original(writer, rendered)

        def pages():
            for index, (width, height, color) in enumerate(specs):
                # Eager list(images) would ask for page two before page one was
                # configured/painted, violating this streaming assertion.
                if index:
                    self.assertEqual(configured[-1], specs[index - 1][:2])
                yield image(width, height, color)

        with patch.object(exports, '_pdf_page_size', side_effect=configure):
            output = exports.images_to_pdf_bytes(pages(), title='三枚のノート')
        with pymupdf.open(stream=output, filetype='pdf') as document:
            self.assertEqual(document.page_count, 3)
            self.assertEqual(document.metadata['title'], '三枚のノート')
            for index, (width, height, color) in enumerate(specs):
                page = document[index]
                self.assertAlmostEqual(page.rect.width / page.rect.height, width / height, delta=.003)
                raster = page.get_pixmap()
                self.assertEqual(raster.pixel(2, 2)[:3], (255, 255, 255))
                center = raster.pixel(raster.width // 2, raster.height // 2)[:3]
                expected = QColor(color)
                self.assertTrue(all(abs(actual - target) <= 2 for actual, target in
                                    zip(center, (expected.red(), expected.green(), expected.blue()))))

    def test_empty_invalid_later_and_excessive_page_streams_are_rejected(self):
        with self.assertRaises(ValueError):
            exports.images_to_pdf_bytes(iter(()))
        with self.assertRaises(ValueError):
            exports.images_to_pdf_bytes(iter((image(40, 30, '#3478dc'), QImage())))
        with patch.object(exports, 'MAX_PAGES', 1), self.assertRaises(ValueError):
            exports.images_to_pdf_bytes(image(40, 30, '#3478dc') for _ in range(2))


if __name__ == '__main__':
    unittest.main()
