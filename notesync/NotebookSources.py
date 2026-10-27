"""Public saved-notebook data and PDF export CLI; independent of LMS clients."""
import argparse
import json
import os
from pathlib import Path
import sys
from .NotebookStorage import note_digest, read_library

def store_path():
    from .Paths import default_library
    return default_library()

def read_notes(path=None):
    source = Path(path or store_path()).resolve()
    data = read_library(source)
    return source, [n for n in data['notes'] if not n.get('deletedAt')]

def list_sources():
    path, notes = read_notes()
    return {'store_path': str(path), 'notes': [dict(note_id=n['id'], title=n['title'],
            course=n.get('course', '未分類'), pages=len(n.get('pages') or [n]),
            content_hash=note_digest(n), attachments=n.get('attachments', [])) for n in notes]}

def _render(snapshot, output):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import QRectF, Qt
    from .NotebookExports import _notes, images_to_pdf_bytes
    from .NotebookPaper import paint_paper
    from .NotebookText import prepare_text, paint_note_texts
    from .InkModel import Stroke, paint_ink
    app = QApplication.instance() or QApplication([])
    raw_note = json.loads(Path(snapshot).read_text())
    # The PDF is notebook pages only. Attachment bytes remain separate sources.
    raw_note.pop('attachments', None)
    note = _notes([raw_note])[0]
    def images():
        for page in note.get('pages') or [note]:
            width, height = 1600, round(1600 / page['aspect'])
            image = QImage(width, height, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = QRectF(0, 0, width, height)
            paint_paper(painter, rect, page['paper'])
            for raw in page['strokes']:
                paint_ink(painter, Stroke(**raw), rect)
            paint_note_texts(painter, [prepare_text(t, page['aspect']) for t in page.get('texts', [])], rect)
            painter.end()
            yield image
    Path(output).write_bytes(images_to_pdf_bytes(images(), title=note['title']))


def main():
    parser = argparse.ArgumentParser(description='Export a saved notebook JSON snapshot to PDF')
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    _render(args.snapshot, args.output)

if __name__ == '__main__':
    main()
