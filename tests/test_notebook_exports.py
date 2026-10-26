from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pymupdf as fitz
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter

from beamerplus import NotebookExports as notebook_exports
from beamerplus.NotebookExports import (
    MAX_BACKUP_BYTES,
    create_notebook_backup,
    image_to_pdf_bytes,
    image_to_png_bytes,
    parse_notebook_backup,
)

TEXT_ANNOTATIONS_AVAILABLE = notebook_exports._prepare_text is not None


def sample_note(identifier='note_original'):
    return {'id': identifier, 'title': '応用代数学 — Galois 🖋', 'paper': 'grid', 'aspect': 4 / 3,
            'createdAt': '2026-10-26T17:19:00+09:00', 'updated_at': 1_793_000_000,
            'strokes': [{'color': '#3478dc', 'brush': 'fountain', 'width_ratio': .004,
                         'opacity': .8, 'points': [[.1, .2, .6], [.2, .3, 1]]}],
            'texts': [{'id': 'text_original', 'text': '応用代数学\nÉvariste Galois — π',
                       'norm_x': .1, 'norm_y': .2, 'size': 18, 'color': '#202124'}]}


def payload(notes=None, **extra):
    return json.dumps({'format': 'spennotes', 'version': 1,
                       'activeId': 'note_original', 'notes': notes or [sample_note()], **extra},
                      ensure_ascii=True).encode('utf-8')


class NotebookExportTests(unittest.TestCase):
    @unittest.skipUnless(TEXT_ANNOTATIONS_AVAILABLE, 'Optional text annotations are not installed')
    def test_collection_roundtrip_preserves_ink_text_and_metadata(self):
        notes = [sample_note(), sample_note('note_second')]
        notes[1].update(title='別のノート', paper='ruled', aspect=.75)
        source = deepcopy(notes)
        backup = create_notebook_backup(notes, active_id='note_second')
        decoded = json.loads(backup)
        self.assertEqual(decoded['format'], 'spennotes')
        self.assertEqual(decoded['version'], 1)
        restored = parse_notebook_backup(backup, existing_notes=notes)
        self.assertEqual(len(restored['notes']), 2)
        self.assertEqual(restored['activeId'], restored['notes'][1]['id'])
        for before, after in zip(notes, restored['notes']):
            for field in ('title', 'paper', 'aspect', 'createdAt', 'updated_at', 'strokes'):
                self.assertEqual(before[field], after[field])
            self.assertNotEqual(before['id'], after['id'])
            self.assertNotEqual(before['texts'][0]['id'], after['texts'][0]['id'])
            self.assertEqual({**{k: v for k, v in before['texts'][0].items() if k != 'id'},
                              'format': before['texts'][0].get('format', 'auto')},
                             {k: v for k, v in after['texts'][0].items() if k != 'id'})
        self.assertEqual(notes, source)

    def test_single_note_backup_selects_only_requested_note(self):
        notes = [sample_note(), sample_note('note_second')]
        for note in notes:
            note.pop('texts')
        backup = json.loads(create_notebook_backup(notes, active_id='note_original', note_id='note_second'))
        self.assertEqual([note['id'] for note in backup['notes']], ['note_second'])
        self.assertEqual(backup['activeId'], 'note_second')
        with self.assertRaises(ValueError):
            create_notebook_backup(notes, note_id='not_present')

    @unittest.skipUnless(TEXT_ANNOTATIONS_AVAILABLE, 'Optional text annotations are not installed')
    def test_exports_whitelist_data_and_omit_credentials_and_private_paths(self):
        note = sample_note()
        note.update(api_key='sk-ant-secret', mcp_token='mcp-secret', path='/home/private/notebooks.json')
        note['strokes'][0]['private_path'] = '/secret/stroke'
        note['texts'][0]['token'] = 'text-token'
        data = create_notebook_backup([note]).decode('utf-8')
        for secret in ('sk-ant-secret', 'mcp-secret', '/home/private', '/secret', 'text-token', 'api_key', 'mcp_token'):
            self.assertNotIn(secret, data)
        self.assertIn('応用代数学', data)

    @unittest.skipUnless(TEXT_ANNOTATIONS_AVAILABLE, 'Optional text annotations are not installed')
    def test_duplicate_source_ids_are_replaced_and_imports_never_reuse_existing_ids(self):
        notes = [sample_note(), sample_note()]
        notes[0]['texts'].append(deepcopy(notes[0]['texts'][0]))
        existing = [sample_note('already_here')]
        original = deepcopy(existing)
        first = parse_notebook_backup(payload(notes), existing_notes=existing)
        second = parse_notebook_backup(payload(notes), existing_notes=existing + first['notes'])
        new_ids = []
        for note in first['notes'] + second['notes']:
            new_ids.append(note['id'])
            new_ids.extend(item['id'] for item in note['texts'])
        self.assertEqual(len(set(new_ids)), len(new_ids))
        self.assertFalse({'note_original', 'text_original', 'already_here'} & set(new_ids))
        self.assertEqual(existing, original)

    def test_malformed_later_note_is_rejected_without_mutating_any_inputs(self):
        existing = [sample_note('keep_me')]
        notes = [sample_note(), sample_note('bad')]
        for note in notes:
            note.pop('texts')
        notes[1]['strokes'][0]['points'] = [[.2, float('inf'), .5]]
        previous = deepcopy(existing)
        with self.assertRaises(ValueError):
            parse_notebook_backup(payload(notes), existing_notes=existing)
        self.assertEqual(existing, previous)
        expected = sample_note()
        expected.pop('texts')
        self.assertEqual(notes[0], expected)

    @unittest.skipUnless(TEXT_ANNOTATIONS_AVAILABLE, 'Optional text annotations are not installed')
    def test_invalid_styles_numbers_structure_and_text_are_rejected(self):
        modifications = [
            lambda n: n.update(aspect=0),
            lambda n: n.update(paper='unknown'),
            lambda n: n.update(title='bad\x00title'),
            lambda n: n.update(title='bad\ud800title'),
            lambda n: n['strokes'][0].update(color='url(https://example.com)'),
            lambda n: n['strokes'][0].update(brush='untrusted'),
            lambda n: n['strokes'][0].update(width_ratio=True),
            lambda n: n['strokes'][0].update(opacity=-1),
            lambda n: n['strokes'][0].update(points=[]),
            lambda n: n['strokes'][0].update(points=[[.1]]),
            lambda n: n['strokes'][0].update(points=[[.1, .2, 2]]),
            lambda n: n['strokes'][0].update(points=[[.1, 500]]),
            lambda n: n['texts'][0].update(norm_x=1),
            lambda n: n['texts'][0].update(norm_x=10 ** 1000),
            lambda n: n['texts'][0].update(size=100),
            lambda n: n['texts'][0].update(text='bad\ud800text'),
            lambda n: n.update(createdAt='/private/path'),
        ]
        for modify in modifications:
            note = sample_note()
            modify(note)
            with self.subTest(modification=modify), self.assertRaises(ValueError):
                parse_notebook_backup(payload([note]))

    def test_file_version_size_unicode_and_duplicate_json_key_validation(self):
        for data in (b'', b'not JSON', b'\xff', b'{"version":1,"version":1}',
                     payload(version=2), payload(version=True), payload(format='different'),
                     b' ' * (MAX_BACKUP_BYTES + 1)):
            with self.subTest(data=data[:50]), self.assertRaises(ValueError):
                parse_notebook_backup(data)

    def test_collection_and_cross_note_point_budgets_are_enforced(self):
        first, second = sample_note(), sample_note('second')
        first.pop('texts')
        second.pop('texts')
        with self.assertRaises(ValueError):
            parse_notebook_backup(payload([first for _ in range(201)]))
        with patch('beamerplus.NotebookExports.MAX_POINTS', 3), self.assertRaises(ValueError):
            parse_notebook_backup(payload([first, second]))
        with patch('beamerplus.NotebookExports.MAX_STROKES', 1), self.assertRaises(ValueError):
            parse_notebook_backup(payload([first, second]))

    def test_collection_roundtrip_preserves_trash_and_live_note_status(self):
        live, trashed = sample_note(), sample_note('trashed_note')
        for note in (live, trashed):
            note.pop('texts')
        live['deletedAt'] = None
        trashed['deletedAt'] = '2026-10-26T18:45:00Z'
        before = deepcopy([live, trashed])
        backup = create_notebook_backup([live, trashed], active_id=trashed['id'])
        exported = json.loads(backup)
        self.assertIsNone(exported['notes'][0]['deletedAt'])
        self.assertEqual(exported['notes'][1]['deletedAt'], trashed['deletedAt'])
        restored = parse_notebook_backup(backup, existing_notes=[live, trashed])
        self.assertIsNone(restored['notes'][0]['deletedAt'])
        self.assertEqual(restored['notes'][1]['deletedAt'], trashed['deletedAt'])
        self.assertEqual(restored['activeId'], restored['notes'][1]['id'])
        self.assertEqual([live, trashed], before)

    def test_trash_timestamp_validation_rejects_malformed_backups(self):
        for stamp in (False, -1, float('inf'), '/private/path', 'not-a-date', '2500-01-01T00:00:00Z'):
            note = sample_note()
            note.pop('texts')
            note['deletedAt'] = stamp
            with self.subTest(timestamp=stamp), self.assertRaises(ValueError):
                parse_notebook_backup(payload([note]))
            with self.subTest(export_timestamp=stamp), self.assertRaises(ValueError):
                create_notebook_backup([note])
        note['deletedAt'] = 1_793_000_000
        restored = parse_notebook_backup(create_notebook_backup([note]))
        self.assertEqual(restored['notes'][0]['deletedAt'], note['deletedAt'])

    @unittest.skipUnless(TEXT_ANNOTATIONS_AVAILABLE, 'Optional text annotations are not installed')
    def test_import_does_not_alias_stroke_or_text_data(self):
        source = sample_note()
        restored = parse_notebook_backup(create_notebook_backup([source]))['notes'][0]
        restored['strokes'][0]['points'][0][0] = .9
        restored['texts'][0]['text'] = 'changed'
        self.assertEqual(source['strokes'][0]['points'][0][0], .1)
        self.assertEqual(source['texts'][0]['text'], '応用代数学\nÉvariste Galois — π')

    def test_legacy_two_coordinate_strokes_remain_compatible(self):
        note = sample_note()
        note.pop('texts')
        del note['strokes'][0]['brush']
        note['strokes'][0]['points'] = [[.1, .2], [.3, .4]]
        restored = parse_notebook_backup(create_notebook_backup([note]))['notes'][0]
        self.assertEqual(restored['strokes'][0]['brush'], 'pen')
        self.assertEqual(restored['strokes'][0]['points'], [[.1, .2], [.3, .4]])

    def test_png_has_white_paper_and_preserves_drawn_content(self):
        image = QImage(400, 300, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.fillRect(QRect(100, 100, 100, 100), QColor('#3478dc'))
        painter.end()
        output = image_to_png_bytes(image)
        restored = QImage.fromData(output)
        self.assertTrue(output.startswith(b'\x89PNG'))
        self.assertEqual((restored.width(), restored.height()), (400, 300))
        self.assertEqual(restored.pixelColor(10, 10).name(), '#ffffff')
        self.assertEqual(restored.pixelColor(150, 150).name(), '#3478dc')

    def test_pdf_is_single_page_aspect_correct_white_and_contains_ink(self):
        for width, height in ((400, 300), (300, 400)):
            image = QImage(width, height, QImage.Format.Format_ARGB32)
            image.fill(QColor(0, 0, 0, 0))
            painter = QPainter(image)
            painter.fillRect(QRect(width // 4, height // 4, width // 2, height // 2), QColor('#3478dc'))
            painter.end()
            output = image_to_pdf_bytes(image, title='応用代数学')
            with fitz.open(stream=output, filetype='pdf') as document:
                self.assertEqual(document.page_count, 1)
                page = document[0]
                self.assertAlmostEqual(page.rect.width / page.rect.height, width / height, delta=.003)
                self.assertEqual(document.metadata['title'], '応用代数学')
                rendered = page.get_pixmap()
                self.assertEqual(rendered.pixel(2, 2)[:3], (255, 255, 255))
                center = rendered.pixel(rendered.width // 2, rendered.height // 2)[:3]
                self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(center, (52, 120, 220))))

    def test_null_images_are_rejected(self):
        for function in (image_to_png_bytes, image_to_pdf_bytes):
            with self.subTest(function=function), self.assertRaises(ValueError):
                function(QImage())


class NotebookExportWithoutTextTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'beamerplus' / 'NotebookExports.py'
        spec = importlib.util.spec_from_file_location('exports_without_optional_text_test', source)
        self.exports = importlib.util.module_from_spec(spec)
        # Simulate an older installation without deleting or modifying another
        # worker's optional NotebookText.py in the shared checkout.
        with patch.dict(sys.modules, {'beamerplus.NotebookText': None}):
            spec.loader.exec_module(self.exports)

    def test_ink_backup_roundtrip_works_without_optional_text_module(self):
        self.assertIsNone(self.exports._prepare_text)
        note = sample_note()
        note.pop('texts')
        before = deepcopy(note)
        data = self.exports.create_notebook_backup([note], active_id=note['id'])
        restored = self.exports.parse_notebook_backup(data, existing_notes=[note])
        self.assertEqual(restored['notes'][0]['strokes'], note['strokes'])
        self.assertEqual(restored['notes'][0]['title'], note['title'])
        self.assertEqual(restored['notes'][0]['texts'], [])
        self.assertNotEqual(restored['notes'][0]['id'], note['id'])
        self.assertEqual(note, before)

    def test_rendered_image_exports_work_without_optional_text_module(self):
        image = QImage(40, 30, QImage.Format.Format_RGB32)
        image.fill(QColor('#3478dc'))
        self.assertTrue(self.exports.image_to_png_bytes(image).startswith(b'\x89PNG'))
        self.assertTrue(self.exports.image_to_pdf_bytes(image).startswith(b'%PDF-'))

    def test_text_backups_are_explicitly_rejected_instead_of_silently_losing_text(self):
        existing = [sample_note('keep_me')]
        before = deepcopy(existing)
        with self.assertRaisesRegex(ValueError, '文字'):
            self.exports.parse_notebook_backup(payload(), existing_notes=existing)
        with self.assertRaisesRegex(ValueError, '文字'):
            self.exports.create_notebook_backup([sample_note()])
        self.assertEqual(existing, before)


if __name__ == '__main__':
    unittest.main()
