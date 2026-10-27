import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from beamerplus.NotebookModel import NotebookStore
from beamerplus.NotebookStorage import DirectoryLibrary, read_library, sha, atomic, note_digest
from beamerplus.NotebookExports import create_notebook_backup, parse_notebook_backup

class DirectoryStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = NotebookStore(self.root / 'library')
        self.store.save()

    def note_path(self):
        entries = json.loads((self.root / 'library/index.json').read_text())['notes']
        return self.root / 'library' / next(e['path'] for e in entries if e['id'] == self.store.active_id)

    def attach(self):
        raw = b'%PDF-fixture'
        self.store.active['attachments'] = [dict(id='document', name='配布資料.pdf', data=base64.b64encode(raw).decode(), sha256=sha(raw))]
        self.store.save()
        return raw

    def test_migration_preserves_all_data_and_original(self):
        legacy = self.root / 'other/notebooks.json'; legacy.parent.mkdir()
        original = NotebookStore(legacy)
        original.active['title'] = '流体力学'
        original.new_page(); original.new_note('ごみ箱')['deletedAt'] = '2026-10-27T00:00:00Z'
        original.save(); raw = legacy.read_bytes()
        migrated = NotebookStore(legacy.parent / 'library')
        self.assertEqual([note_digest(n) for n in original.notes], [note_digest(n) for n in migrated.notes])
        self.assertEqual(migrated.active_id, original.active_id)
        self.assertEqual(legacy.read_bytes(), raw)
        self.assertEqual(next((legacy.parent / 'library/.history').glob('legacy-*')).read_bytes(), raw)
        original.active['title'] = 'old app changed'; original.save()
        with self.assertRaisesRegex(OSError, '旧ノート'): migrated.save()

    def test_course_move_trash_and_restore_keep_attachment_bytes(self):
        raw = self.attach(); first = self.note_path()
        self.store.active['course'] = '流体力学'; self.store.save()
        self.assertNotEqual(first, self.note_path()); self.assertFalse(first.exists())
        self.assertEqual(self.store.read_attachment(self.store.active, 'document')[1], raw)
        self.store.active['deletedAt'] = '2026-10-27T00:00:00Z'; self.store.save()
        self.assertIn('/trash/', str(self.note_path()))
        self.store.active['deletedAt'] = None; self.store.save()
        loaded = NotebookStore(self.store.path)
        self.assertEqual(loaded.read_attachment(loaded.active, 'document')[1], raw)
        self.assertEqual(loaded.active['course'], '流体力学')

    def test_portable_backup_carries_course_and_attachment_without_paths(self):
        raw = self.attach(); self.store.active['course'] = '力学'; self.store.save()
        data = create_notebook_backup(self.store.portable_notes())
        self.assertNotIn(str(self.root).encode(), data)
        restored = parse_notebook_backup(data, existing_notes=self.store.notes)['notes'][0]
        self.assertEqual(restored['course'], '力学')
        self.assertNotEqual(restored['attachments'][0]['id'], 'document')
        self.assertEqual(base64.b64decode(restored['attachments'][0]['data']), raw)
        self.store.notes.append(restored); self.store.save()
        self.assertEqual(self.store.read_attachment(restored, restored['attachments'][0]['id'])[1], raw)

    def test_interrupted_commit_recovers_previous_revision(self):
        before = deepcopy(self.store.notes)
        self.store.active['title'] = 'uncommitted'
        def fail_index(path, data):
            if Path(path).name == 'index.json': raise OSError('disk full')
            return atomic(path, data)
        with patch('beamerplus.NotebookStorage.atomic', side_effect=fail_index):
            with self.assertRaises(OSError): self.store.save()
        self.assertEqual(read_library(self.store.path)['notes'], before)
        self.store.save()
        self.assertEqual(NotebookStore(self.store.path).active['title'], 'uncommitted')

    def test_concurrent_stale_writer_cannot_overwrite_and_lock_recovers(self):
        second = NotebookStore(self.store.path)
        self.store.active['title'] = 'first'; self.store.save()
        second.active['title'] = 'stale'
        with self.assertRaises(OSError): second.save()
        with self.store.directory.lock():
            with self.assertRaises(OSError): NotebookStore(self.store.path).save()
        self.store.save()
        self.assertEqual(NotebookStore(self.store.path).active['title'], 'first')

    def test_noop_does_not_rewrite_note_and_history_is_bounded(self):
        path = self.note_path(); before = path.stat().st_mtime_ns
        self.store.save(); self.assertEqual(path.stat().st_mtime_ns, before)
        for number in range(16):
            self.store.active['title'] = str(number); self.store.save()
        self.assertLessEqual(len(list((path.parent / '.history').glob('*.json'))), 10)

    def test_bad_index_path_and_corrupt_attachment_are_rejected(self):
        self.attach()
        item = self.store.active['attachments'][0]
        (self.note_path().parent / item['file']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '一致'): self.store.read_attachment(self.store.active, 'document')
        index = self.store.path / 'index.json'; data = json.loads(index.read_text())
        data['notes'][0]['path'] = '../../outside/note.json'; index.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'パス'): read_library(self.store.path)

    def test_public_pdf_export_keeps_original_and_all_pages(self):
        self.attach(); self.store.new_page(); self.store.save()
        source = self.note_path(); before = source.read_bytes(); output = self.root / 'answer.pdf'
        run = subprocess.run([sys.executable, '-m', 'beamerplus.NotebookSources', str(source), str(output)], capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr.decode())
        import pymupdf
        with pymupdf.open(output) as pdf: self.assertEqual(pdf.page_count, 2)
        self.assertEqual(source.read_bytes(), before)

if __name__ == '__main__': unittest.main()
