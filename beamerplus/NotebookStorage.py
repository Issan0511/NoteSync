"""Version-2 notebook library: course folders, one note JSON, and attachments.

The atomic index is the commit point. Every indexed note revision is also kept
in its folder's .history so interrupted multi-note writes remain readable.
No GUI, LMS, model API or credential dependency.
"""
from contextlib import contextmanager
from copy import deepcopy
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid


MAX_ATTACHMENT = 10 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def label(value, default='未分類'):
    if value is None or value == '': return default
    if (not isinstance(value, str) or not value.strip() or len(value) > 120
            or value in ('.', '..') or any(c in value for c in '/\\')
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('科目名・ファイル名にはパスや制御文字を使えません。')
    return value.strip()


def slug(value):
    clean = re.sub(r'[<>:"|?*]', '_', value).strip('. ') or '無題'
    return clean[:40] + '-' + sha(value.encode())[:8]


def note_digest(note):
    pages = note.get('pages') or [note]
    content = {'id': note['id'], 'title': note['title'], 'pages': [
        {k: p.get(k) for k in ('id', 'strokes', 'texts', 'paper', 'aspect')} for p in pages]}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_library(path):
    """Public disk contract. Reads v1 JSON or the v2 index and verified revisions."""
    path = Path(path)
    index = path / 'index.json' if path.is_dir() else path
    data = json.loads(index.read_text())
    if data.get('version') == 1:
        return data
    if data.get('version') != 2 or not isinstance(data.get('notes'), list):
        raise ValueError('ノート一覧の形式を確認してください。')
    root, notes = index.parent.resolve(), []
    for entry in data['notes']:
        relative = Path(entry['path'])
        target = (root / relative).resolve()
        if relative.is_absolute() or not target.is_relative_to(root) or target.name != 'note.json':
            raise ValueError('ノート一覧に無効なパスがあります。')
        expected = entry['sha256']
        if not re.fullmatch(r'[0-9a-f]{64}', expected): raise ValueError('ノートのハッシュが不正です。')
        raw = target.read_bytes() if target.exists() else b''
        if sha(raw) != expected:
            raw = (target.parent / '.history' / (expected + '.json')).read_bytes()
        if sha(raw) != expected: raise ValueError('保存したノートの内容が一致しません。')
        note = json.loads(raw)
        if note['id'] != entry['id']: raise ValueError('ノートIDが一致しません。')
        notes.append(note)
    return {'version': 1, 'activeId': data.get('activeId'), 'notes': notes}


class DirectoryLibrary:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.index = self.root / 'index.json'
        self.expected_index = sha(self.index.read_bytes()) if self.index.exists() else None

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / '.write-lock'
        stream = path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if path.stat().st_size == 0:
                    stream.write(b'0'); stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            raise OSError('別のノート保存が実行中です。') from None
        try:
            yield
        finally:
            # OS locks are released even when the app crashes. Keep the lock
            # inode: unlinking it lets competing writers lock different files.
            stream.close()

    def _check_legacy(self):
        if not self.index.exists(): return
        migration = json.loads(self.index.read_text()).get('migration')
        if migration:
            source = Path(migration['source'])
            if source.exists() and sha(source.read_bytes()) != migration['sha256']:
                raise OSError('移行後に旧ノートが更新されています。両方のデータを保持しました。旧アプリを終了して変更を取り込んでください。')

    def load(self):
        self._check_legacy()
        return read_library(self.root) if self.index.exists() else None

    def _entries(self):
        return {e['id']: e for e in json.loads(self.index.read_text()).get('notes', [])} if self.index.exists() else {}

    def _attachment(self, item, previous_folder=None):
        name = label(item['name'], '添付資料')
        if 'data' in item:
            try:
                if len(item['data']) > MAX_ATTACHMENT * 4 // 3 + 4: raise ValueError()
                raw = base64.b64decode(item['data'], validate=True)
            except (ValueError, TypeError):
                raise ValueError('添付資料のデータを読み取れません。') from None
        else:
            if previous_folder is None: raise ValueError('添付資料の保存元がありません。')
            relative = Path(item['file'])
            target = (previous_folder / relative).resolve()
            if relative.is_absolute() or not target.is_relative_to(previous_folder.resolve()):
                raise ValueError('添付資料のパスが不正です。')
            raw = target.read_bytes()
        if not raw or len(raw) > MAX_ATTACHMENT: raise ValueError('添付資料は1個10MiB以内です。')
        checksum = sha(raw)
        if item.get('sha256', checksum) != checksum: raise ValueError('添付資料の内容が一致しません。')
        relative = 'attachments/' + checksum + '-' + slug(name)
        # Retain the original extension for normal desktop file opening.
        extension = Path(name).suffix[:15]
        if extension: relative += extension
        return {'id': item.get('id') or uuid.uuid4().hex, 'name': name, 'file': relative,
                'sha256': checksum, 'bytes': len(raw)}, raw

    def save(self, notes, active_id, *, migration=None):
        with self.lock():
            self._check_legacy()
            current = sha(self.index.read_bytes()) if self.index.exists() else None
            if current != self.expected_index:
                raise OSError('別のアプリがノートを保存しました。再読み込みが必要です。')
            old = self._entries()
            entries, clean_notes = [], []
            for original in notes:
                note = deepcopy(original)
                identifier = note['id']
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', identifier): raise ValueError('無効なノートIDです。')
                course = label(note.get('course'))
                note['course'] = course
                # Stable ID avoids breaking paths when a note is renamed.
                folder = Path('trash' if note.get('deletedAt') else 'courses')
                if not note.get('deletedAt'): folder /= slug(course)
                folder /= identifier
                target = self.root / folder
                previous = self.root / old[identifier]['path'] if identifier in old else None
                attachments = []
                for item in note.get('attachments', []):
                    metadata, raw = self._attachment(item, previous.parent if previous else None)
                    location = target / metadata['file']
                    if not location.exists() or sha(location.read_bytes()) != metadata['sha256']:
                        atomic(location, raw)
                    attachments.append(metadata)
                note['attachments'] = attachments
                raw = encoded(note); checksum = sha(raw)
                history = target / '.history' / (checksum + '.json')
                if not history.exists(): atomic(history, raw)
                # Keep the old committed revision recoverable before changing head.
                if not (target / 'note.json').exists() or sha((target / 'note.json').read_bytes()) != checksum:
                    atomic(target / 'note.json', raw)
                entries.append({'id': identifier, 'title': note['title'], 'course': course,
                                'path': str(folder / 'note.json'), 'sha256': checksum,
                                'deletedAt': note.get('deletedAt')})
                clean_notes.append(note)
            index = {'version': 2, 'activeId': active_id, 'notes': entries}
            if migration is not None: index['migration'] = migration
            elif self.index.exists():
                previous_migration = json.loads(self.index.read_text()).get('migration')
                if previous_migration: index['migration'] = previous_migration
            content = encoded(index)
            if current != sha(content): atomic(self.index, content)
            self.expected_index = sha(content)
            # After the commit, move old course/trash locations to recoverable history.
            new_paths = {e['path'] for e in entries}
            for entry in old.values():
                if entry['path'] in new_paths: continue
                prior = (self.root / entry['path']).parent
                if prior.exists():
                    try:
                        archive = self.root / '.history' / 'moved' / uuid.uuid4().hex
                        archive.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(prior, archive)
                    except OSError:
                        pass  # Old redundant files never invalidate a committed save.
            for entry in entries:
                history = (self.root / entry['path']).parent / '.history'
                try:
                    revisions = sorted(history.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
                    for prior in revisions[10:]:
                        if prior.stem != entry['sha256']: prior.unlink()
                except OSError:
                    pass  # Maintenance failures occur after the save committed.
            return clean_notes

    def migrate(self, legacy):
        """First-launch import; original file and a byte-for-byte backup are retained."""
        if self.index.exists(): return
        legacy = Path(legacy)
        if not legacy.exists(): return
        raw = legacy.read_bytes()
        data = json.loads(raw)
        if data.get('version') != 1 or not isinstance(data.get('notes'), list):
            raise ValueError('移行元ノートの形式を確認してください。')
        # Validate the whole library before the new index becomes authoritative.
        from .NotebookModel import NotebookStore
        validated = NotebookStore(legacy)
        backup = self.root / '.history' / ('legacy-' + sha(raw) + '.json')
        if not backup.exists(): atomic(backup, raw)
        if legacy.read_bytes() != raw:
            raise OSError('移行中に旧ノートが更新されました。旧アプリを終了してから再起動してください。')
        saved = self.save(validated.notes, validated.active_id, migration={'source': str(legacy.resolve()), 'sha256': sha(raw)})
        if read_library(self.root)['notes'] != saved:
            raise OSError('移行後のノートを読み戻せませんでした。')

    def portable_notes(self, notes):
        entries = self._entries()
        result = deepcopy(notes)
        for note in result:
            folder = (self.root / entries[note['id']]['path']).parent if note['id'] in entries else None
            for item in note.get('attachments', []):
                _, raw = self._attachment(item, folder)
                item['data'] = base64.b64encode(raw).decode()
                item.pop('file', None)
        return result

    def read_attachment(self, note, attachment_id):
        item = next((a for a in note.get('attachments', []) if a['id'] == attachment_id), None)
        if item is None: raise ValueError('添付資料がありません。')
        entry = self._entries()[note['id']]
        _, raw = self._attachment(item, (self.root / entry['path']).parent)
        return item['name'], raw
