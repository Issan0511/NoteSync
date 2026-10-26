"""Persistent notebooks and undoable ink edits, independent of PDF pages."""

from copy import deepcopy
from dataclasses import asdict
import json
import hashlib
import os
from pathlib import Path
import tempfile
import uuid

from beamerplus.DrawingModel import PresentationController, Stroke


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
            self.active_id = data.get('activeId')
        if not self.notes:
            self.new_note()
        if not any(n['id'] == self.active_id for n in self.notes):
            self.active_id = self.notes[0]['id']

    @property
    def active(self):
        return next(note for note in self.notes if note['id'] == self.active_id)

    def new_note(self, title='新しいノート'):
        note = {'id': uuid.uuid4().hex, 'title': title[:120], 'paper': 'plain', 'aspect': 4 / 3, 'strokes': []}
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

    def snapshot(self):
        return deepcopy(self.sketchbook_strokes)

    def begin_edit(self):
        if self.pending_edit is None:
            self.pending_edit = self.snapshot()

    def finish_edit(self):
        if self.pending_edit is not None and self.pending_edit != self.sketchbook_strokes:
            self.undo_stack.append(self.pending_edit)
            self.undo_stack = self.undo_stack[-40:]
            self.redo_stack.clear()
        self.pending_edit = None
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
            self.sketchbook_strokes = self.undo_stack.pop()
            self.sketchbook_history = []
            self.strokes_updated.emit(-1)

    def redo(self):
        self.end_stroke()
        if self.redo_stack:
            self.undo_stack.append(self.snapshot())
            self.sketchbook_strokes = self.redo_stack.pop()
            self.sketchbook_history = []
            self.strokes_updated.emit(-1)

    def load_ink(self, data):
        self.current_stroke = None
        self.pending_edit = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.sketchbook_strokes = [Stroke(**stroke) for stroke in data]
        self.sketchbook_texts = []
        self.sketchbook_history = []
        self.strokes_updated.emit(-1)

    def serialized_ink(self):
        return [asdict(stroke) for stroke in self.sketchbook_strokes]
