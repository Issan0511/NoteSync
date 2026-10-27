"""Data migration and operation without optional tutor installation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from notesync import Paths


class DataMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        env = patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        platform = patch.object(Paths.sys, 'platform', 'linux')
        platform.start()
        self.addCleanup(platform.stop)
        self.old = self.root / 'BeamerPlus Notes'
        self.old.mkdir()
        (self.old / 'notebooks.json').write_text('{"version":1,"notes":[]}')
        (self.old / 'mcp-connection.json').write_text('not copied')

    def test_verified_copy_keeps_original_and_does_not_copy_connection(self):
        target = Paths.migrate_data()
        self.assertEqual(target.name, 'NoteSync')
        self.assertEqual((target / 'notebooks.json').read_bytes(), (self.old / 'notebooks.json').read_bytes())
        self.assertFalse((target / 'mcp-connection.json').exists())
        self.assertEqual(Paths.migrate_data(), target)
        (self.old / 'notebooks.json').write_text('newer original')
        with self.assertRaisesRegex(OSError, '旧アプリ'):
            Paths.migrate_data()
        self.assertEqual(json.loads((target / 'notebooks.json').read_text())['version'], 1)

    def test_existing_library_is_never_overwritten(self):
        target = self.root / 'NoteSync'
        target.mkdir()
        (target / 'notebooks.json').write_text('keep current')
        Paths.migrate_data()
        self.assertEqual((target / 'notebooks.json').read_text(), 'keep current')

    def test_failed_copy_does_not_publish_partial_library(self):
        with patch.object(Paths.shutil, 'copy2', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): Paths.migrate_data()
        self.assertFalse((self.root / 'NoteSync').exists())
        self.assertEqual(list(self.root.glob('.notesync-migration-*')), [])
        self.assertTrue((self.old / 'notebooks.json').exists())

    def test_connection_prefers_new_name_with_legacy_fallback(self):
        with patch.dict(os.environ, {'NOTESYNC_MCP_FILE': '', 'BEAMERPLUS_MCP_FILE': ''}):
            self.assertEqual(Paths.default_connection_file().parent, self.old)
            target = Paths.migrate_data()
            (target / 'mcp-connection.json').write_text('new')
            self.assertEqual(Paths.default_connection_file().parent, target)


class CoreIsolationTests(unittest.TestCase):
    def test_core_window_and_export_import_without_provider_or_slideshow(self):
        script = '''
import importlib.abc, sys
class NoTutor(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith(('note_tutor', 'beamerplus', 'dotenv')):
            raise AssertionError('Core imported ' + fullname)
sys.meta_path.insert(0, NoTutor())
from notesync.NotebookWindow import NotebookWindow
from notesync.TabletNotebook import NOTEBOOK_HTML
from notesync.NotebookSources import _render
assert 'assistant-panel' not in NOTEBOOK_HTML
assert 'function handleExtensionMessage' in NOTEBOOK_HTML
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                                env=dict(os.environ, NOTESYNC_DISABLE_EXTENSIONS='1'), timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
