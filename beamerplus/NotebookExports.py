"""Portable notebook backups and image/PDF exports without application secrets.

The backup parser returns detached data; callers choose when to append the
validated notes to their store. Importing never replaces an existing note.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import re
import unicodedata
import uuid

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QImage, QPageSize, QPainter, QPdfWriter, QPixmap

try:
    from beamerplus.NotebookText import prepare_text as _prepare_text
except ModuleNotFoundError as exc:
    if exc.name != 'beamerplus.NotebookText':
        raise
    # Text annotations are an optional extension. Older notebook installs can
    # still back up/restore ink and export rendered images without that module.
    _prepare_text = None


MAX_BACKUP_BYTES = 10 * 1024 * 1024
MAX_NOTES = 200
MAX_STROKES = 50_000
MAX_POINTS = 500_000
MAX_TEXTS_PER_NOTE = 200
MAX_TEXTS = 10_000
_COLOR = re.compile(r'#[0-9a-fA-F]{6}')
_IDENTIFIER = re.compile(r'[a-zA-Z0-9_-]{1,128}')
_TIMESTAMPS = ('createdAt', 'updatedAt', 'created_at', 'updated_at')


def _number(value, lower, upper):
    if type(value) not in (int, float):
        raise ValueError('ノートの数値データが正しくありません。')
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError('ノートの数値データが正しくありません。') from exc
    if not math.isfinite(number) or not lower <= number <= upper:
        raise ValueError('ノートの数値データが正しくありません。')
    return number


def _title(value):
    if (not isinstance(value, str) or not value.strip() or len(value) > 120
            or any(unicodedata.category(char) in ('Cc', 'Cs') for char in value)):
        raise ValueError('ノート名を1〜120文字で指定してください。')
    return value


def _identifier(value):
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError('ノートの識別子が正しくありません。')
    return value


def _timestamp(value):
    if type(value) in (int, float):
        # Accept Unix seconds or milliseconds without converting the source.
        _number(value, 0, 7_258_118_400_000)
        return value
    if isinstance(value, str) and len(value) <= 40:
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            pass
        else:
            if 1970 <= parsed.year <= 2200:
                return value
    raise ValueError('ノートの日付データが正しくありません。')


def _stroke(data, budget):
    if not isinstance(data, dict):
        raise ValueError('筆跡のデータが正しくありません。')
    color, brush = data.get('color'), data.get('brush', 'pen')
    if (not isinstance(color, str) or _COLOR.fullmatch(color) is None
            or brush not in ('pen', 'fountain', 'pencil', 'highlighter')):
        raise ValueError('筆跡の色・ペンの種類が正しくありません。')
    raw_points = data.get('points')
    if not isinstance(raw_points, (list, tuple)) or not 1 <= len(raw_points) <= 100_000:
        raise ValueError('筆跡の点数が正しくありません。')
    budget['points'] += len(raw_points)
    budget['strokes'] += 1
    if budget['points'] > MAX_POINTS or budget['strokes'] > MAX_STROKES:
        raise ValueError('バックアップの筆跡が多すぎます。ノートを分けて保存してください。')
    points = []
    for point in raw_points:
        if not isinstance(point, (list, tuple)) or len(point) not in (2, 3):
            raise ValueError('筆跡の座標データが正しくありません。')
        result = [_number(point[0], -4, 5), _number(point[1], -4, 5)]
        if len(point) == 3:
            result.append(_number(point[2], 0, 1))
        points.append(result)
    return {'color': color, 'brush': brush,
            'width_ratio': _number(data.get('width_ratio'), .0001, .8),
            'opacity': _number(data.get('opacity'), .05, 1), 'points': points}


def _notes(data):
    if not isinstance(data, (list, tuple)) or not 1 <= len(data) <= MAX_NOTES:
        raise ValueError('バックアップは1〜200冊のノートで指定してください。')
    result, budget = [], {'points': 0, 'strokes': 0, 'texts': 0}
    for raw in data:
        if not isinstance(raw, dict):
            raise ValueError('ノートの形式が正しくありません。')
        identifier = _identifier(raw.get('id'))
        aspect = _number(raw.get('aspect', 4 / 3), .4, 2.5)
        paper = raw.get('paper', 'plain')
        if paper not in ('plain', 'ruled', 'grid'):
            raise ValueError('ノートの用紙設定が正しくありません。')
        strokes, texts = raw.get('strokes'), raw.get('texts', [])
        if not isinstance(strokes, list) or not isinstance(texts, list) or len(texts) > MAX_TEXTS_PER_NOTE:
            raise ValueError('ノートの筆跡・文字データが正しくありません。')
        if texts and _prepare_text is None:
            raise ValueError('このバージョンでは文字入りノートを読み書きできません。文字機能のあるバージョンを使用してください。')
        budget['texts'] += len(texts)
        if budget['texts'] > MAX_TEXTS:
            raise ValueError('バックアップの文字が多すぎます。ノートを分けて保存してください。')
        note = {'id': identifier, 'title': _title(raw.get('title')), 'paper': paper,
                'aspect': aspect, 'strokes': [_stroke(item, budget) for item in strokes], 'texts': []}
        for raw_text in texts:
            if not isinstance(raw_text, dict):
                raise ValueError('ノートの文字データが正しくありません。')
            text = raw_text.get('text')
            if isinstance(text, str) and any(unicodedata.category(char) == 'Cs' for char in text):
                raise ValueError('ノートの文字データが正しくありません。')
            # Whitelisting prevents auxiliary API/MCP fields and private paths
            # from leaking into exported JSON even if a caller supplies them.
            allowed = {key: raw_text[key] for key in ('id', 'text', 'norm_x', 'norm_y', 'size', 'color') if key in raw_text}
            try:
                note['texts'].append(asdict(_prepare_text(allowed, aspect)))
            except (TypeError, OverflowError) as exc:
                raise ValueError('ノートの文字データが正しくありません。') from exc
        for key in _TIMESTAMPS:
            if key in raw:
                note[key] = _timestamp(raw[key])
        if 'deletedAt' in raw:
            note['deletedAt'] = None if raw['deletedAt'] is None else _timestamp(raw['deletedAt'])
        result.append(note)
    return result


def create_notebook_backup(notes, *, active_id=None, note_id=None):
    """Return a secret-free ``.spennotes`` version-1 backup as UTF-8 bytes.

    ``note_id`` exports only that note; omitting it exports the collection.
    Notes, strokes and text annotations are copied without changing the source.
    """
    if not isinstance(notes, (list, tuple)):
        raise ValueError('保存するノートの一覧が正しくありません。')
    selected = notes
    if note_id is not None:
        selected = [note for note in notes if isinstance(note, dict) and note.get('id') == note_id]
        if len(selected) != 1:
            raise ValueError('保存するノートが見つかりません。')
        active_id = note_id
    sanitized = _notes(selected)
    if active_id is None or not any(note['id'] == active_id for note in sanitized):
        active_id = sanitized[0]['id']
    payload = {'format': 'spennotes', 'version': 1,
               'exportedAt': datetime.now(timezone.utc).isoformat(),
               'activeId': active_id, 'notes': sanitized}
    try:
        output = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (UnicodeError, ValueError) as exc:
        raise ValueError('ノートの文字データを保存できませんでした。') from exc
    if len(output) > MAX_BACKUP_BYTES:
        raise ValueError('バックアップは10 MiBまでです。ノートごとに分けて保存してください。')
    return output


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('バックアップに重複した項目があります。')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('バックアップに使用できない数値が含まれています。')


def _fresh_id(used):
    for _ in range(1024):
        identifier = uuid.uuid4().hex
        if identifier not in used:
            used.add(identifier)
            return identifier
    raise ValueError('ノートの新しい識別子を作れませんでした。もう一度お試しください。')


def parse_notebook_backup(data, *, existing_notes=()):
    """Validate a complete backup, returning detached notes with fresh IDs.

    Returns ``{'notes': [...], 'activeId': '...'}``. Append these notes only
    after this function succeeds. Existing notes and all source IDs are kept
    untouched; every imported note and text receives a new unique identifier.
    """
    try:
        if isinstance(data, str):
            raw = data.encode('utf-8')
        elif isinstance(data, (bytes, bytearray, memoryview)):
            raw = bytes(data)
        else:
            raise ValueError('バックアップのファイル形式が正しくありません。')
        if not raw or len(raw) > MAX_BACKUP_BYTES:
            raise ValueError('読み込めるバックアップは10 MiBまでです。')
        payload = json.loads(raw.decode('utf-8'), object_pairs_hook=_json_object, parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('バックアップを読み込めませんでした。ファイルの形式を確認してください。') from exc
    if (not isinstance(payload, dict) or type(payload.get('version')) is not int or payload['version'] != 1
            or payload.get('format', 'spennotes') != 'spennotes'):
        raise ValueError('このバックアップのバージョンには対応していません。')
    sanitized = _notes(payload.get('notes'))
    used = set()
    for note in [*existing_notes, *sanitized]:
        if not isinstance(note, dict):
            continue
        if isinstance(note.get('id'), str):
            used.add(note['id'])
        for item in note.get('texts', []):
            if isinstance(item, dict) and isinstance(item.get('id'), str):
                used.add(item['id'])
    active_id, source_active = None, payload.get('activeId')
    for note in sanitized:
        original_id = note['id']
        note['id'] = _fresh_id(used)
        if active_id is None and original_id == source_active:
            active_id = note['id']
        for item in note['texts']:
            item['id'] = _fresh_id(used)
    return {'notes': sanitized, 'activeId': active_id or sanitized[0]['id']}


def _image(image):
    if isinstance(image, QPixmap):
        image = image.toImage()
    if (not isinstance(image, QImage) or image.isNull() or image.width() > 16_384
            or image.height() > 16_384 or image.width() * image.height() > 64_000_000):
        raise ValueError('保存するノート画像の大きさを確認してください。')
    return image


def image_to_png_bytes(image):
    """Encode an already rendered QImage/QPixmap as a white-paper PNG."""
    image = _image(image)
    flattened = QImage(image.width(), image.height(), QImage.Format.Format_RGB32)
    flattened.fill(Qt.GlobalColor.white)
    painter = QPainter(flattened)
    painter.drawImage(0, 0, image)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        if not flattened.save(buffer, 'PNG'):
            raise ValueError('ノート画像を保存できませんでした。')
        return bytes(data)
    finally:
        buffer.close()


def image_to_pdf_bytes(image, *, title=''):
    """Encode one rendered page with exact source aspect and a white background.

    The longer paper edge is 297 mm. The supplied image already contains the
    note's paper, ink and text, so this helper does not inspect application data.
    """
    image = _image(image)
    if title:
        title = _title(title)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QPdfWriter(buffer)
    writer.setCreator('SpenNotes')
    if title:
        writer.setTitle(title)
    writer.setResolution(144)
    longest = max(image.width(), image.height())
    size = QSizeF(297 * image.width() / longest, 297 * image.height() / longest)
    writer.setPageSize(QPageSize(size, QPageSize.Unit.Millimeter, 'SpenNotes', QPageSize.SizeMatchPolicy.ExactMatch))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    painter = QPainter(writer)
    if not painter.isActive():
        buffer.close()
        raise ValueError('ノートのPDFを作成できませんでした。')
    try:
        target = QRectF(0, 0, writer.width(), writer.height())
        painter.fillRect(target, Qt.GlobalColor.white)
        painter.drawImage(target, image)
    finally:
        painter.end()
    del writer
    buffer.close()
    output = bytes(data)
    if not output.startswith(b'%PDF-'):
        raise ValueError('ノートのPDFを作成できませんでした。')
    return output
