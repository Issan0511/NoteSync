"""Persistent notebooks and undoable ink edits, independent of PDF pages."""

from copy import deepcopy
from dataclasses import asdict
import json
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile
import uuid

from beamerplus.DrawingModel import PresentationController, Stroke
from beamerplus.NotebookText import NoteText, prepare_text


class InkEditConflict(ValueError):
    """The selected ink no longer matches the client's displayed revision."""


def _finite_number(value, lower, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('選択した線の編集データが正しくありません。')
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError('選択した線の編集データが正しくありません。') from exc
    if not math.isfinite(number) or not lower <= number <= upper:
        raise ValueError('選択した線の編集データが正しくありません。')
    return number


def _edit_matrix(data, default=None):
    matrix = data.get('matrix', default if default is not None else [1, 0, 0, 1, 0, 0])
    if not isinstance(matrix, (list, tuple)) or len(matrix) != 6:
        raise ValueError('選択した線の移動データが正しくありません。')
    return [_finite_number(value, -16, 16) for value in matrix]


def _transform_stroke(stroke, matrix, width_scale):
    a, b, c, d, e, f = matrix
    result = deepcopy(stroke)
    result.points = [(_finite_number(a * point[0] + c * point[1] + e, -4, 5),
                      _finite_number(b * point[0] + d * point[1] + f, -4, 5),
                      *point[2:]) for point in stroke.points]
    result.width_ratio = _finite_number(stroke.width_ratio * width_scale, .0001, .8)
    return result


def _clipboard_stroke(data):
    if not isinstance(data, dict) or set(data) - {'color', 'width_ratio', 'opacity', 'points', 'brush'}:
        raise ValueError('貼り付ける線のデータが正しくありません。')
    color = data.get('color')
    brush = data.get('brush', 'pen')
    if not isinstance(color, str) or re.fullmatch(r'#[0-9a-fA-F]{6}', color) is None or brush not in ('pen', 'fountain', 'pencil', 'highlighter'):
        raise ValueError('貼り付ける線のスタイルが正しくありません。')
    raw_points = data.get('points')
    if not isinstance(raw_points, list) or not 1 <= len(raw_points) <= 100000:
        raise ValueError('貼り付ける線の点数が正しくありません。')
    points = []
    for point in raw_points:
        if not isinstance(point, (tuple, list)) or len(point) not in (2, 3):
            raise ValueError('貼り付ける線の座標が正しくありません。')
        points.append((_finite_number(point[0], -4, 5), _finite_number(point[1], -4, 5),
                       _finite_number(point[2] if len(point) == 3 else 1, 0, 1)))
    return Stroke(color=color, width_ratio=_finite_number(data.get('width_ratio'), .0001, .8),
                  opacity=_finite_number(data.get('opacity'), .05, 1), points=points, brush=brush)


class NotebookStore:
    def __init__(self, path):
        self.path = Path(path)
        self.notes = []
        self.active_id = None
        if self.path.exists():
            data = json.loads(self.path.read_text())
            if data.get('version') != 1 or not isinstance(data.get('notes'), list):
                raise ValueError('ノート保存ファイルの形式を確認してください')
            self.notes = data['notes']
            for note in self.notes:
                if not isinstance(note.get('id'), str) or not isinstance(note.get('strokes'), list):
                    raise ValueError('ノート保存ファイルの形式を確認してください')
                for stroke in note['strokes']:
                    Stroke(**stroke)
                if not isinstance(note.get('texts', []), list):
                    raise ValueError('ノートの文字データを確認してください')
                note['texts'] = [asdict(prepare_text(item, note.get('aspect', 4 / 3))) for item in note.get('texts', [])]
            self.active_id = data.get('activeId')
        if not self.notes:
            self.new_note()
        if not any(n['id'] == self.active_id for n in self.notes):
            self.active_id = self.notes[0]['id']

    @property
    def active(self):
        return next(note for note in self.notes if note['id'] == self.active_id)

    def new_note(self, title='新しいノート'):
        note = {'id': uuid.uuid4().hex, 'title': title[:120], 'paper': 'plain', 'aspect': 4 / 3, 'strokes': [], 'texts': []}
        self.notes.insert(0, note)
        self.active_id = note['id']
        return note

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps({'version': 1, 'activeId': self.active_id, 'notes': self.notes}, ensure_ascii=False)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.path.parent, delete=False) as output:
                temporary = output.name
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def import_ink(self, strokes, aspect=16 / 9):
        if not strokes:
            return
        tag = hashlib.sha256(json.dumps(strokes, sort_keys=True).encode()).hexdigest()
        if any(note.get('importTag') == tag for note in self.notes):
            return
        if len(self.notes) == 1 and not self.notes[0]['strokes'] and self.notes[0]['title'] == '新しいノート':
            note = self.active
        else:
            note = self.new_note()
        note.update(title='引き継いだノート', strokes=strokes, aspect=aspect, importTag=tag)


class NotebookController(PresentationController):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_sketchbook = True
        self.current_tool = 'pen'
        self.pen_color = '#202124'
        self.pen_opacity = 1.0
        self.undo_stack = []
        self.redo_stack = []
        self.pending_edit = None
        self.pending_texts = None
        self.undo_text_stack = []
        self.redo_text_stack = []
        self.ink_revision = 0
        # Connect before a view/server attaches: every published mutation carries
        # its new revision, including changes while another pen is still down.
        for signal in (self.stroke_started, self.stroke_added_point, self.stroke_line_updated,
                       self.strokes_updated, self.strokes_cleared, self.texts_updated):
            signal.connect(self._advance_ink_revision)

    def _advance_ink_revision(self, *args):
        self.ink_revision += 1

    def snapshot(self):
        return deepcopy(self.sketchbook_strokes)

    def begin_edit(self):
        if self.pending_edit is None:
            self.pending_edit = self.snapshot()
            self.pending_texts = deepcopy(self.sketchbook_texts)

    def finish_edit(self):
        if self.pending_edit is not None and (self.pending_edit != self.sketchbook_strokes or self.pending_texts != self.sketchbook_texts):
            self.undo_stack.append(self.pending_edit)
            self.undo_stack = self.undo_stack[-40:]
            self.undo_text_stack.append(self.pending_texts)
            self.undo_text_stack = self.undo_text_stack[-40:]
            self.redo_stack.clear()
            self.redo_text_stack.clear()
        self.pending_edit = None
        self.pending_texts = None
        self.sketchbook_history = []

    def begin_custom_stroke(self, *args, **kwargs):
        self.finish_edit()
        self.begin_edit()
        super().begin_custom_stroke(*args, **kwargs)

    def end_stroke(self):
        super().end_stroke()
        self.finish_edit()

    def erase_at_point(self, *args, **kwargs):
        self.begin_edit()
        return super().erase_at_point(*args, **kwargs)

    def clear_current_page_strokes(self):
        self.finish_edit()
        self.begin_edit()
        super().clear_current_page_strokes()
        self.finish_edit()

    def undo_current_page_stroke(self):
        self.end_stroke()
        if self.undo_stack:
            self.redo_stack.append(self.snapshot())
            self.redo_text_stack.append(deepcopy(self.sketchbook_texts))
            self.sketchbook_strokes = self.undo_stack.pop()
            self.sketchbook_texts = self.undo_text_stack.pop()
            self.sketchbook_history = []
            self.texts_updated.emit(-1)
            self.strokes_updated.emit(-1)

    def redo(self):
        self.end_stroke()
        if self.redo_stack:
            self.undo_stack.append(self.snapshot())
            self.undo_text_stack.append(deepcopy(self.sketchbook_texts))
            self.sketchbook_strokes = self.redo_stack.pop()
            self.sketchbook_texts = self.redo_text_stack.pop()
            self.sketchbook_history = []
            self.texts_updated.emit(-1)
            self.strokes_updated.emit(-1)

    def load_ink(self, data, texts=None):
        self.current_stroke = None
        self.pending_edit = None
        self.pending_texts = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.undo_text_stack.clear()
        self.redo_text_stack.clear()
        self.sketchbook_strokes = [Stroke(**stroke) for stroke in data]
        self.sketchbook_texts = [NoteText(**item) for item in (texts or [])]
        self.sketchbook_history = []
        self.strokes_updated.emit(-1)

    def serialized_ink(self):
        return [asdict(stroke) for stroke in self.sketchbook_strokes]

    def serialized_texts(self):
        return [asdict(item) for item in self.sketchbook_texts]

    def add_note_text(self, data, aspect=4 / 3):
        item = prepare_text(data, aspect)
        if len(self.sketchbook_texts) >= 200:
            raise ValueError('このノートの文字が多すぎます。不要な書き込みを消してください。')
        if any(existing.id == item.id for existing in self.sketchbook_texts):
            raise ValueError('この識別子の文字はすでに追加されています。')
        self.end_stroke()
        self.begin_edit()
        self.sketchbook_texts.append(item)
        self.finish_edit()
        self.texts_updated.emit(-1)
        return item

    def remove_note_text(self, identifier):
        remaining = [item for item in self.sketchbook_texts if item.id != identifier]
        if remaining == self.sketchbook_texts:
            raise ValueError('指定した文字が見つかりません。ノートを読み直してください。')
        self.end_stroke()
        self.begin_edit()
        self.sketchbook_texts = remaining
        self.finish_edit()
        self.texts_updated.emit(-1)

    def apply_ink_edit(self, data):
        """Validate a selection edit completely, then commit it as one undo step.

        Matrix ordering follows Canvas 2D: x' = ax + cy + e, y' = bx + dy + f.
        Indices refer to the exact ink_revision the client selected.
        """
        revision = data.get('baseRevision')
        if type(revision) is not int or revision != self.ink_revision:
            raise InkEditConflict('ノートの線が更新されました。もう一度囲んで選択してください。')
        action = data.get('action')
        if action not in ('transform', 'delete', 'duplicate', 'style', 'paste'):
            raise ValueError('選択した線の操作が正しくありません。')
        raw_indices = data.get('indices', [])
        if not isinstance(raw_indices, list) or len(raw_indices) > 10000 or any(type(index) is not int or not 0 <= index < len(self.sketchbook_strokes) for index in raw_indices):
            raise ValueError('選択した線が見つかりません。もう一度選択してください。')
        indices = sorted(set(raw_indices))
        if action != 'paste' and not indices:
            raise ValueError('編集する線を囲んで選択してください。')

        edited = self.snapshot()
        selected = [edited[index] for index in indices]
        if action in ('transform', 'duplicate', 'paste'):
            default_matrix = [1, 0, 0, 1, .02, .02] if action == 'duplicate' else None
            matrix = _edit_matrix(data, default_matrix)
            width_scale = _finite_number(data.get('widthScale', 1), .1, 10)
        if action == 'transform':
            for index in indices:
                edited[index] = _transform_stroke(edited[index], matrix, width_scale)
        elif action == 'delete':
            selected_indices = set(indices)
            edited = [stroke for index, stroke in enumerate(edited) if index not in selected_indices]
            indices = []
        elif action in ('duplicate', 'paste'):
            if action == 'paste':
                raw_strokes = data.get('strokes')
                if not isinstance(raw_strokes, list) or not 1 <= len(raw_strokes) <= 1000:
                    raise ValueError('貼り付ける線の数が正しくありません。')
                if sum(len(stroke.get('points', [])) if isinstance(stroke, dict) and isinstance(stroke.get('points'), list) else 100001 for stroke in raw_strokes) > 100000:
                    raise ValueError('一度に貼り付ける線が多すぎます。')
                selected = [_clipboard_stroke(stroke) for stroke in raw_strokes]
            additions = [_transform_stroke(stroke, matrix, width_scale) for stroke in selected]
            indices = list(range(len(edited), len(edited) + len(additions)))
            edited.extend(additions)
        elif action == 'style':
            style = {}
            if 'color' in data:
                color = data['color']
                if not isinstance(color, str) or re.fullmatch(r'#[0-9a-fA-F]{6}', color) is None:
                    raise ValueError('線の色が正しくありません。')
                style['color'] = color
            if 'opacity' in data:
                style['opacity'] = _finite_number(data['opacity'], .1, 1)
            if 'widthRatio' in data:
                style['width_ratio'] = _finite_number(data['widthRatio'], .0005, .08)
            if not style:
                raise ValueError('変更する線のスタイルを選んでください。')
            for stroke in selected:
                for key, value in style.items():
                    setattr(stroke, key, value)

        # Invalid requests never finish a pen gesture or disturb its undo state.
        self.end_stroke()
        if edited != self.sketchbook_strokes:
            self.begin_edit()
            self.sketchbook_strokes = edited
            self.finish_edit()
            self.strokes_updated.emit(-1)
        return indices
