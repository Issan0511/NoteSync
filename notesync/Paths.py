"""Stable data paths and a one-time, verified copy from the former app name."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def app_data_base():
    if sys.platform == 'darwin': return Path.home() / 'Library/Application Support'
    if sys.platform == 'win32': return Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))


def data_root(): return app_data_base() / 'NoteSync'
def legacy_root(): return app_data_base() / 'BeamerPlus Notes'


def default_connection_file():
    explicit = os.environ.get('NOTESYNC_MCP_FILE') or os.environ.get('BEAMERPLUS_MCP_FILE')
    if explicit: return Path(explicit)
    current = data_root() / 'mcp-connection.json'
    legacy = legacy_root() / 'mcp-connection.json'
    return current if current.exists() or not legacy.exists() else legacy


def default_library():
    explicit = os.environ.get('NOTESYNC_NOTEBOOK_PATH') or os.environ.get('BEAMERPLUS_NOTEBOOK_PATH')
    if explicit: return Path(explicit)
    for root in (data_root(), legacy_root()):
        if root == data_root(): check_legacy_copy(root)
        if (root / 'library/index.json').exists(): return root / 'library'
        if (root / 'notebooks.json').exists(): return root / 'notebooks.json'
    return data_root() / 'library'


def migrate_data():
    """Called by the editor before creating its bridge. Never moves the original."""
    target, source = data_root(), legacy_root()
    if target.exists():
        check_legacy_copy(target)
        return target
    paths = [p for p in (source / 'notebooks.json', source / 'library') if p.exists()]
    if not paths: return target
    def manifest():
        files = [child for p in paths for child in (p.rglob('*') if p.is_dir() else [p]) if child.is_file()]
        return {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    before = manifest()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.notesync-migration-', dir=target.parent))
    try:
        for p in paths:
            if p.is_dir(): shutil.copytree(p, temporary / p.name)
            else: shutil.copy2(p, temporary / p.name)
        after = {relative: hashlib.sha256((temporary / relative).read_bytes()).hexdigest() for relative in before}
        if before != after or before != manifest():
            raise OSError('旧ノートが更新中です。旧アプリを終了してからNoteSyncを起動してください。')
        # Atomic publication; another startup must not replace an existing library.
        if target.exists(): raise OSError('別のNoteSyncが起動しました。起動し直してください。')
        (temporary / 'migration.json').write_text(json.dumps(dict(source=str(source), files=before)))
        temporary.rename(target)
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
    return target


def check_legacy_copy(root):
    marker = Path(root) / 'migration.json'
    if not marker.exists(): return
    migration = json.loads(marker.read_text())
    for relative, expected in migration['files'].items():
        path = Path(migration['source']) / relative
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise OSError('旧アプリのノートが更新されています。両方を保持しました。旧アプリを終了し、変更を統合してください。')
