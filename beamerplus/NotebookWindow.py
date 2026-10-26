"""Notebook-only desktop host for the tablet, ink storage, and Claude settings."""

from dataclasses import asdict
import json
import os
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt, QTimer, QStandardPaths, QRectF, QPointF
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import QMainWindow, QToolBar, QPushButton, QLabel, QFileDialog, QMessageBox

from beamerplus.MainWindow import MainWindow
from beamerplus.NotebookModel import NotebookController, NotebookStore
from beamerplus.NotebookLibrary import NotebookLibraryMixin
from beamerplus.NotebookFiles import NotebookFilesMixin
from beamerplus.SlideCanvas import SlideCanvas
from beamerplus.DrawingModel import paint_ink
from beamerplus.WebServer import WebBridge, WebServer


class NotebookCanvas(SlideCanvas):
    def _get_slide_rect(self):
        aspect = getattr(self, 'aspect', 4 / 3)
        width = max(1, min(self.width() - 40, (self.height() - 40) * aspect))
        height = width / aspect
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#ebebee'))
        rect = self._get_slide_rect()
        paint_paper(painter, rect, getattr(self, 'paper', 'plain'))
        for stroke in self.controller.sketchbook_strokes:
            paint_ink(painter, stroke, rect)
        painter.end()


class NotebookWindow(NotebookFilesMixin, NotebookLibraryMixin, MainWindow):
    def __init__(self, store_path=None, import_state=None, http_port=8080, ws_port=8765):
        QMainWindow.__init__(self)
        self.setWindowTitle('BeamerPlus Notes')
        self.resize(1200, 850)
        self.controller = NotebookController(self)
        self.viewer = None
        self.pdf_reader = None
        self._is_handling_web_stroke = False
        self._web_erase_active = False
        default_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / 'notebooks.json'
        path = Path(store_path or os.environ.get('BEAMERPLUS_NOTEBOOK_PATH', default_path))
        self.store = NotebookStore(path)
        if import_state:
            self.store.import_ink(import_state.get('sketchbookStrokes', []) or import_state.get('strokes', []))
        self._init_notebook_library()
        self._document_id = self.store.active_id
        self.canvas = NotebookCanvas(self.controller)
        self.canvas.aspect = self.store.active.get('aspect', 4 / 3)
        self.canvas.paper = self.store.active.get('paper', 'plain')
        self.slide_view = SimpleNamespace(canvas=self.canvas)
        self.setCentralWidget(self.canvas)
        self.controller.load_ink(self.store.active['strokes'])
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(600)
        self.save_timer.timeout.connect(self.save_notebook)
        self.erase_timer = QTimer(self)
        self.erase_timer.setSingleShot(True)
        self.erase_timer.setInterval(350)
        self.erase_timer.timeout.connect(self.controller.finish_edit)
        self.web_bridge = WebBridge()
        self.web_server = WebServer(self.web_bridge, lambda page: None, self._get_web_status,
                                    http_port=http_port, ws_port=ws_port)
        self._connect_web_signals()
        self.web_bridge.notebook_command.connect(self._on_notebook_command)
        self.web_bridge.erase_started.connect(self._begin_web_erase)
        self.web_bridge.erase_ended.connect(self._finish_erase)
        self.web_bridge.redo_requested.connect(self.controller.redo)
        self.web_bridge.client_count_changed.connect(self._finalize_disconnected_ink)
        for signal in (self.controller.stroke_finished, self.controller.strokes_updated, self.controller.strokes_cleared):
            signal.connect(self._ink_changed)
        self._create_menus_and_toolbars()
        self.setStyleSheet('QMainWindow { background:#e9e9ed; } QToolBar {background:#fff; spacing:12px; padding:12px; border:0;} QPushButton {padding:8px 12px; border:1px solid #ddd; border-radius:8px; background:white; color:#24262b;} QLabel {color:#35373d;}')
        self.save_notebook()
        self.web_server.start()

    def _create_menus_and_toolbars(self):
        self.main_toolbar = QToolBar('ノート', self)
        self.main_toolbar.setMovable(False)
        self.addToolBar(self.main_toolbar)
        self.title_label = QLabel(self.store.active['title'])
        self.title_label.setStyleSheet('font-size:18px;font-weight:600;')
        self.main_toolbar.addWidget(self.title_label)
        for text, callback in [('＋ 新しいノート', lambda: self._on_notebook_command({'type': 'note_new'})),
                               ('↶ 戻す', self.controller.undo), ('↷ やり直す', self.controller.redo),
                               ('画像で保存', self.export_notebook)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            self.main_toolbar.addWidget(button)
        self.btn_ipad_connect = QPushButton('タブレット接続 · QR')
        self.btn_ipad_connect.clicked.connect(self.show_ipad_dialog)
        self.main_toolbar.addWidget(self.btn_ipad_connect)
        button = QPushButton('✦ Claude設定')
        button.clicked.connect(self.show_ai_settings)
        self.main_toolbar.addWidget(button)
        self.save_label = QLabel('保存済み')
        self.main_toolbar.addWidget(self.save_label)
        for label, shortcut, callback in [('保存', QKeySequence.StandardKey.Save, self.save_notebook),
                                          ('元に戻す', QKeySequence.StandardKey.Undo, self.controller.undo),
                                          ('やり直す', QKeySequence.StandardKey.Redo, self.controller.redo)]:
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            self.addAction(action)

    def _tb_btn_style(self):
        return 'QPushButton {padding:8px 12px;border:1px solid #ddd;border-radius:8px;background:white;color:#24262b;}'

    def _ink_changed_legacy(self, *args):
        self.save_label.setText('保存中…')
        self.save_timer.start()

    def _save_notebook_legacy(self):
        self.store.active['strokes'] = self.controller.serialized_ink()
        try:
            self.store.save()
            self.save_label.setText('保存済み')
            self.web_server.broadcast({'type': 'note_saved', 'noteId': self.store.active_id})
            self.web_server.broadcast({'type': 'note_history', 'canUndo': bool(self.controller.undo_stack or self.controller.pending_edit is not None), 'canRedo': bool(self.controller.redo_stack)})
            return True
        except OSError:
            self.save_label.setText('保存できません。保存先を確認してください')
            self.web_server.broadcast({'type': 'note_error', 'message': 'PCへの保存に失敗しました。保存先を確認してください。'})
            return False

    def _on_notebook_command_legacy(self, data):
        kind = data.get('type')
        if kind == 'note_ink_edit':
            self._on_ink_edit(data)
            return
        if kind in ('note_new', 'note_select'):
            target = str(data.get('id', ''))
            if kind == 'note_select' and not any(note['id'] == target for note in self.store.notes):
                return
            self.controller.end_stroke()
            self._finish_erase()
            self.save_notebook()
            if kind == 'note_new':
                self.store.new_note()
            else:
                self.store.active_id = target
            self._document_id = self.store.active_id
            self.canvas.aspect = self.store.active.get('aspect', 4 / 3)
            self.canvas.paper = self.store.active.get('paper', 'plain')
            self.controller.load_ink(self.store.active['strokes'])
            self.title_label.setText(self.store.active['title'])
            self.save_notebook()
        elif kind == 'note_title':
            target = next((note for note in self.store.notes if note['id'] == data.get('id', self.store.active_id)), None)
            if target is None:
                return
            target['title'] = str(data.get('title', ''))[:120].strip() or '無題のノート'
            self.title_label.setText(self.store.active['title'])
            self.save_notebook()
        elif kind == 'note_paper' and data.get('paper') in ('plain', 'ruled', 'grid'):
            self.store.active['paper'] = data['paper']
            self.canvas.paper = data['paper']
            self.canvas.update()
            self.save_notebook()
        elif kind == 'note_save':
            self.save_notebook()
        self.web_server.broadcast(dict(self._get_web_status(), type='state_sync'))

    def _on_ink_edit(self, data):
        try:
            if data.get('documentId') != self.store.active_id:
                raise ValueError('別のノートが開かれています。もう一度囲んで選択してください。')
            indices = self.controller.apply_ink_edit(data)
            self._finish_erase()
        except (ValueError, TypeError, OverflowError) as exc:
            self.web_server.broadcast({'type': 'note_error', 'message': str(exc)})
            self.web_server.broadcast(dict(self._get_web_status(), type='state_sync'))
            self.web_server.broadcast({'type': 'note_ink_edit_result', 'ok': False,
                                       'documentId': self.store.active_id, 'inkRevision': self.controller.ink_revision,
                                       'requestId': data.get('requestId'), 'indices': []})
            return
        # Send the complete resulting ink before its selection indices. This also
        # acknowledges no-op transforms, which do not emit a mutation signal.
        self._sync_web_strokes_updated(-1)
        self.web_server.broadcast({'type': 'note_ink_edit_result', 'ok': True,
                                   'documentId': self.store.active_id, 'inkRevision': self.controller.ink_revision,
                                   'requestId': data.get('requestId'), 'indices': indices})
        # No-op edits still need the final saved acknowledgement after the
        # tablet has shown a local pending state. Keep disk work off this slot.
        timer = getattr(self, 'save_timer', None)
        if timer is not None:
            timer.start()

    def _get_web_status_legacy(self):
        return {'documentId': self.store.active_id, 'noteId': self.store.active_id,
                'inkRevision': self.controller.ink_revision,
                'paperAspect': self.store.active.get('aspect', 4 / 3),
                'title': self.store.active['title'], 'paper': self.store.active.get('paper', 'plain'),
                'notes': [{'id': note['id'], 'title': note['title']} for note in self.store.notes],
                'currentPage': 0, 'totalPages': 0, 'isSketchbook': True, 'isSketchVisible': True,
                'strokes': [], 'sketchbookStrokes': self.controller.serialized_ink(),
                'canUndo': bool(self.controller.undo_stack or self.controller.pending_edit is not None),
                'canRedo': bool(self.controller.redo_stack)}

    def _sync_web_strokes_updated(self, index):
        self.web_server.broadcast({'type': 'strokes_updated', 'documentId': self.store.active_id,
                                   'inkRevision': self.controller.ink_revision, 'strokes': self.controller.serialized_ink()})
        self.web_server.broadcast({'type': 'note_history', 'canUndo': bool(self.controller.undo_stack), 'canRedo': bool(self.controller.redo_stack)})

    def _sync_web_stroke_finished(self, index):
        self.web_server.broadcast({'type': 'strokes_updated', 'documentId': self.store.active_id,
                                   'inkRevision': self.controller.ink_revision, 'strokes': self.controller.serialized_ink()})
        QTimer.singleShot(0, lambda: self.web_server.broadcast({'type': 'note_history', 'canUndo': bool(self.controller.undo_stack), 'canRedo': bool(self.controller.redo_stack)}))

    def _sync_web_strokes_cleared(self, index):
        self._sync_web_strokes_updated(index)

    def _on_web_erase_requested(self, data):
        super()._on_web_erase_requested(data)
        if not self._web_erase_active:
            self.erase_timer.start()

    def _begin_web_erase(self):
        self.erase_timer.stop()
        self._web_erase_active = True
        self.controller.begin_edit()

    def _finish_erase(self):
        needs_save_ack = (self._web_erase_active or self.erase_timer.isActive()
                          or self.controller.pending_edit is not None)
        self._web_erase_active = False
        self.erase_timer.stop()
        self.controller.finish_edit()
        self.web_server.broadcast({'type': 'note_history', 'canUndo': bool(self.controller.undo_stack), 'canRedo': bool(self.controller.redo_stack)})
        if needs_save_ack:
            self.save_timer.start()

    def _finalize_disconnected_ink(self, count):
        if count == 0:
            self.controller.end_stroke()
            self._finish_erase()
            self.save_notebook()

    def render_current_page_image_with_sketch(self):
        width, height = 1600, round(1600 / self.store.active.get('aspect', 4 / 3))
        image = QPixmap(width, height)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_paper(painter, QRectF(0, 0, width, height), self.store.active.get('paper', 'plain'))
        for stroke in self.controller.sketchbook_strokes:
            paint_ink(painter, stroke, QRectF(0, 0, width, height))
        painter.end()
        return image

    def export_notebook(self):
        path, _ = QFileDialog.getSaveFileName(self, 'ノートを画像で保存', 'note.png', 'PNG (*.png)')
        if path:
            self.render_current_page_image_with_sketch().save(path, 'PNG')

    def keyPressEvent(self, event):
        QMainWindow.keyPressEvent(self, event)

    def _on_web_page_command(self, *args):
        pass

    def closeEvent(self, event):
        self.controller.end_stroke()
        self._finish_erase()
        if not self.save_notebook():
            event.ignore()
            return
        self.web_server.stop()
        QMainWindow.closeEvent(self, event)


def paint_paper(painter, rect, paper):
    painter.fillRect(rect, Qt.GlobalColor.white)
    if paper == 'plain':
        return
    gap = rect.height() / 24
    painter.setPen(QPen(QColor('#e5e9f0'), .7))
    y = rect.top() + gap
    while y < rect.bottom():
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        y += gap
    if paper == 'grid':
        x = rect.left() + gap
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += gap
