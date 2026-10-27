import math
import time
from PySide6.QtCore import Qt, QPointF, QRectF, QEvent, QSize, QTimer
from PySide6.QtWidgets import QWidget, QLineEdit
from PySide6.QtGui import (
    QPixmap, QPainter, QPaintEvent, QMouseEvent, QTabletEvent,
    QPointingDevice, QColor, QPen, QPainterPath, QRadialGradient, QBrush, QFont
)

from notesync.InkModel import InkController, Stroke, TextItem, create_smooth_path, paint_ink


class InputCanvas(QWidget):
    def __init__(self, controller: InkController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.pixmap: QPixmap | None = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("background-color: #121212;")

        # コントローラシグナル接続
        self.controller.pointer_updated.connect(self._on_pointer_updated)
        self.controller.stroke_started.connect(self._on_stroke_started)
        self.controller.stroke_added_point.connect(self._on_stroke_added_point)
        self.controller.stroke_line_updated.connect(self._on_stroke_line_updated)
        self.controller.stroke_finished.connect(self._on_stroke_finished)
        self.controller.strokes_cleared.connect(self._on_strokes_cleared)
        self.controller.stroke_undone.connect(self._on_stroke_undone)
        self.controller.strokes_updated.connect(self._on_strokes_updated)
        self.controller.text_added.connect(self._on_text_added)
        self.controller.texts_updated.connect(self._on_texts_updated)
        self.controller.tool_changed.connect(self._on_tool_changed)
        self.controller.tool_size_changed.connect(self._on_tool_size_changed)
        self.controller.line_mode_changed.connect(self._on_line_mode_changed)
        self.controller.eraser_mode_changed.connect(self._on_eraser_mode_changed)
        self.controller.color_changed.connect(self._on_color_changed)
        self.controller.blank_state_changed.connect(self._on_blank_state_changed)
        self.controller.sketchbook_state_changed.connect(self._on_sketchbook_state_changed)
        self.controller.sketch_visibility_changed.connect(self._on_sketch_visibility_changed)

        self.pointer_pos: tuple[float, float] | None = None
        self.is_pointer_visible: bool = False
        self.is_pointer_down: bool = False
        self.current_trail: list[tuple[float, float, float]] = []  # 現在ドラッグ中の軌跡 (norm_x, norm_y, timestamp)
        self.fading_trails: list[tuple[list[tuple[float, float, float]], float]] = []  # 離されたフェードアウト中ストローク [(points, release_time), ...]
        self.trail_timer = QTimer(self)
        self.trail_timer.setInterval(20)
        self.trail_timer.timeout.connect(self._on_trail_timer_tick)

        # Wacom / タブレット用状態
        self.is_tablet_drawing: bool = False
        self.hover_pos: tuple[float, float] | None = None

        # インラインテキスト入力用 QLineEdit
        self.text_input = QLineEdit(self)
        self.text_input.hide()
        self.text_input.returnPressed.connect(self._commit_text)
        self.text_input.installEventFilter(self)
        self.text_input_norm_pos: tuple[float, float] | None = None

        # 高品質縮小キャッシュ（面積平均 SmoothTransformation & Retina/HiDPI 対応）
        self._cached_scaled_pixmap: QPixmap | None = None


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()


    def _get_page_rect(self) -> QRectF:
        raise NotImplementedError('Notebook canvas supplies its page rectangle')

    def _pos_to_normalized(self, pos: QPointF) -> tuple[float, float] | None:
        rect = self._get_page_rect()
        if rect.isEmpty():
            return None

        norm_x = (pos.x() - rect.left()) / rect.width()
        norm_y = (pos.y() - rect.top()) / rect.height()

        if 0.0 <= norm_x <= 1.0 and 0.0 <= norm_y <= 1.0:
            return (norm_x, norm_y)
        return None

    def _snap_line_endpoint(self, end_norm: tuple[float, float]) -> tuple[float, float]:
        """水平・垂直方向（±5度以内）の自動スナップ補正"""
        if not self.controller.current_stroke or not self.controller.current_stroke.points:
            return end_norm

        p0 = self.controller.current_stroke.points[0]
        x0, y0 = p0[0], p0[1]
        x1, y1 = end_norm

        rect = self._get_page_rect()
        if rect.isEmpty():
            return end_norm

        # 画面ピクセル基準での差分
        dx_px = (x1 - x0) * rect.width()
        dy_px = (y1 - y0) * rect.height()

        dist_px = math.hypot(dx_px, dy_px)
        if dist_px < 8.0:
            return end_norm

        # 角度判定 (0 ~ 90度)
        angle_deg = math.degrees(math.atan2(abs(dy_px), abs(dx_px)))
        SNAP_DEG = 5.0

        if angle_deg <= SNAP_DEG:
            # 水平線にスナップ（Y座標を始点と同一にする）
            return (x1, y0)
        elif angle_deg >= (90.0 - SNAP_DEG):
            # 垂直線にスナップ（X座標を始点と同一にする）
            return (x0, y1)

        return end_norm

    def _on_pointer_updated(self, nx: float, ny: float, visible: bool, is_down: bool = False):
        self.is_pointer_visible = visible
        prev_down = self.is_pointer_down
        self.is_pointer_down = is_down
        now = time.time()

        if visible:
            self.pointer_pos = (nx, ny)
            if is_down:
                if not prev_down:
                    # 新しいストロークの開始（前のストロークとは完全に分離）
                    if len(self.current_trail) >= 2:
                        self.fading_trails.append((list(self.current_trail), now))
                    self.current_trail = [(nx, ny, now)]
                else:
                    self.current_trail.append((nx, ny, now))
                if not self.trail_timer.isActive():
                    self.trail_timer.start()
            elif prev_down and not is_down:
                # 指・マウスを離した瞬間: 現在のストロークをフェードアウト一覧へ移行
                if len(self.current_trail) >= 2:
                    self.fading_trails.append((list(self.current_trail), now))
                self.current_trail = []
        else:
            self.pointer_pos = None
            if prev_down:
                if len(self.current_trail) >= 2:
                    self.fading_trails.append((list(self.current_trail), now))
                self.current_trail = []

        self.update()

    def _on_trail_timer_tick(self):
        now = time.time()
        lifetime = 0.45      # ドラッグ中の軌跡の寿命（0.45秒）
        fade_duration = 0.25 # 離した後のフェードアウト時間（0.25秒）

        # ドラッグ中ストロークの古い点を削除
        if self.current_trail:
            self.current_trail = [p for p in self.current_trail if now - p[2] < lifetime]

        # 離されてから 0.25秒 経過したフェードアウト中ストロークを削除
        self.fading_trails = [
            (pts, rel_t) for pts, rel_t in self.fading_trails
            if now - rel_t < fade_duration
        ]

        if not self.current_trail and not self.fading_trails:
            self.trail_timer.stop()
        self.update()

    def _on_stroke_started(self, page_index: int, stroke: Stroke):
        self.update()

    def _on_stroke_added_point(self, page_index: int, nx: float, ny: float, pressure: float):
        self.update()

    def _on_stroke_line_updated(self, page_index: int, nx: float, ny: float):
        self.update()

    def _on_stroke_finished(self, page_index: int):
        self.update()

    def _on_strokes_cleared(self, page_index: int):
        self.update()

    def _on_stroke_undone(self, page_index: int):
        self.update()

    def _on_strokes_updated(self, page_index: int):
        self.update()

    def _on_text_added(self, page_index: int, item: TextItem):
        self.update()

    def _on_texts_updated(self, page_index: int):
        self.update()

    def _on_tool_changed(self, tool_name: str):
        if tool_name != "text" and self.text_input.isVisible():
            self._commit_text()
        if tool_name != "pointer":
            self.current_trail.clear()
            self.fading_trails.clear()
            self.trail_timer.stop()
        if tool_name == "text":
            self.setCursor(Qt.CursorShape.IBeamCursor)
        elif tool_name == "hand":
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def eventFilter(self, watched, event):
        if watched == self.text_input:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel_text()
                    return True
                elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._commit_text()
                    return True
            elif event.type() == QEvent.Type.FocusOut:
                if self.text_input.isVisible():
                    self._commit_text()
        return super().eventFilter(watched, event)

    def _commit_text(self):
        if not self.text_input.isVisible() or self.text_input_norm_pos is None:
            return
        text = self.text_input.text().strip()
        norm_x, norm_y = self.text_input_norm_pos
        self.text_input.hide()
        self.text_input.clear()
        self.text_input_norm_pos = None
        if text:
            self.controller.add_text(norm_x, norm_y, text)
        self.setFocus()
        self.update()

    def _cancel_text(self):
        self.text_input.hide()
        self.text_input.clear()
        self.text_input_norm_pos = None
        self.setFocus()
        self.update()

    def _on_tool_size_changed(self, tool_name: str, size: int):
        self.update()

    def _on_line_mode_changed(self, is_line: bool):
        self.update()

    def _on_eraser_mode_changed(self, mode: str):
        self.update()

    def _on_color_changed(self, tool_name: str, color: str):
        self.update()

    def _on_blank_state_changed(self, enabled: bool):
        if enabled:
            self.current_trail.clear()
            self.fading_trails.clear()
            self.trail_timer.stop()
        self.update()

    def _on_sketchbook_state_changed(self, enabled: bool):
        self.update()
        self.update()

    def _on_sketch_visibility_changed(self, visible: bool):
        self.update()

    # ==========================================
    # Wacom / スタイラスペン入力イベント処理
    # ==========================================
    def tabletEvent(self, event: QTabletEvent):
        norm = self._pos_to_normalized(event.position())
        device = event.pointingDevice()
        is_eraser = device is not None and device.pointerType() == QPointingDevice.PointerType.Eraser
        pressure = event.pressure()
        tool = self.controller.current_tool
        ev_type = event.type()

        # 1. 消しゴム機能（ペン尻 または 消しゴムツール選択時）
        if is_eraser or tool == "eraser":
            rect = self._get_page_rect()
            aspect_ratio = rect.width() / rect.height() if rect.height() > 0 else 1.0
            eraser_size = self.controller.get_tool_size("eraser")
            threshold = max(0.008, eraser_size * 0.001)

            if pressure > 0.0 and norm is not None:
                self.controller.erase_at_point(norm[0], norm[1], threshold=threshold, aspect_ratio=aspect_ratio)
            self.hover_pos = norm
            self.update()
            event.accept()
            return

        # 2. レーザーポインタモード（ホバー時はポインタのみ、接地ドラッグ時は一時的な線を描画）
        if tool == "pointer":
            if norm is not None:
                is_down = pressure > 0.05 or bool(event.buttons() & Qt.MouseButton.LeftButton)
                self.controller.update_pointer(norm[0], norm[1], True, is_down=is_down)
            else:
                self.controller.update_pointer(0, 0, False, is_down=False)
            event.accept()
            return

        # 3. 描画ツール（ペン / 蛍光ペン）
        if tool in ("pen", "highlighter"):
            if ev_type == QEvent.Type.TabletPress:
                if norm is not None and pressure > 0.0:
                    self.is_tablet_drawing = True
                    self.hover_pos = None
                    self.controller.begin_stroke(norm[0], norm[1], pressure=pressure)

            elif ev_type == QEvent.Type.TabletMove:
                if pressure > 0.0 and norm is not None:
                    # なぞっている最中
                    if not self.is_tablet_drawing:
                        self.is_tablet_drawing = True
                        self.controller.begin_stroke(norm[0], norm[1], pressure=pressure)
                    else:
                        if self.controller.is_line_mode:
                            snapped = self._snap_line_endpoint(norm)
                            self.controller.update_line_endpoint(snapped[0], snapped[1], pressure=pressure)
                        else:
                            self.controller.add_stroke_point(norm[0], norm[1], pressure=pressure)
                    self.hover_pos = None
                else:
                    # ホバー中
                    if self.is_tablet_drawing:
                        self.is_tablet_drawing = False
                        self.controller.end_stroke()
                    self.hover_pos = norm
                    self.update()

            elif ev_type == QEvent.Type.TabletRelease:
                if self.is_tablet_drawing:
                    self.is_tablet_drawing = False
                    self.controller.end_stroke()
                self.hover_pos = norm
                self.update()

            event.accept()
            return

        # 4. 通常モード（ハンドツール）
        if tool == "hand":
            if ev_type == QEvent.Type.TabletPress and norm is not None:
                if event.button() == Qt.MouseButton.RightButton:
                    self.controller.prev_page()
                else:
                    self.controller.next_page()
            event.accept()
            return

        # 5. テキスト入力ツール
        if tool == "text":
            if ev_type == QEvent.Type.TabletPress and norm is not None and pressure > 0.0:
                self._start_text_input(norm)
            event.accept()
            return

        super().tabletEvent(event)

    # ==========================================
    # 通常マウス操作
    # ==========================================
    def mousePressEvent(self, event: QMouseEvent):
        norm = self._pos_to_normalized(event.position())

        # 既存テキスト入力があり、かつテキストツール以外をクリックした場合は確定
        if self.text_input.isVisible():
            if not norm or self.controller.current_tool != "text":
                self._commit_text()

        if not norm:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            tool = self.controller.current_tool
            if tool == "text":
                self._start_text_input(norm)
                return
            elif tool in ("pen", "highlighter"):
                self.controller.begin_stroke(norm[0], norm[1], pressure=1.0)
            elif tool == "eraser":
                rect = self._get_page_rect()
                aspect_ratio = rect.width() / rect.height() if rect.height() > 0 else 1.0
                eraser_size = self.controller.get_tool_size("eraser")
                threshold = max(0.008, eraser_size * 0.001)
                self.controller.erase_at_point(norm[0], norm[1], threshold=threshold, aspect_ratio=aspect_ratio)
            elif tool == "hand":
                self.controller.next_page()
            elif tool == "pointer":
                self.is_pointer_down = True
                if norm:
                    self.controller.update_pointer(norm[0], norm[1], True, is_down=True)
        elif event.button() == Qt.MouseButton.RightButton:
            self.controller.prev_page()

        super().mousePressEvent(event)

    def _start_text_input(self, norm: tuple[float, float]):
        """クリック位置にインラインテキスト入力ボックスを表示"""
        if self.text_input.isVisible():
            self._commit_text()

        rect = self._get_page_rect()
        if rect.isEmpty():
            return

        base_dim = min(rect.width(), rect.height())
        text_size = self.controller.get_tool_size("text")
        font_size = max(11, int(base_dim * (text_size * 0.0015)))

        font = self.text_input.font()
        font.setPixelSize(font_size)
        font.setBold(False)
        font.setWeight(QFont.Weight.Normal)
        self.text_input.setFont(font)

        text_color = self.controller.get_tool_color("text")
        self.text_input.setStyleSheet(
            f"QLineEdit {{ background-color: rgba(20, 20, 24, 0.92); color: {text_color}; border: 1.5px solid {text_color}; border-radius: 3px; padding: 2px 6px; }}"
        )

        px = rect.left() + norm[0] * rect.width()
        py = rect.top() + norm[1] * rect.height()
        box_w = max(160, int(font_size * 10))
        box_h = int(font_size * 1.8) + 6

        if px + box_w > rect.right():
            px = max(rect.left(), rect.right() - box_w)
        if py + box_h > rect.bottom():
            py = max(rect.top(), rect.bottom() - box_h)

        self.text_input_norm_pos = (
            (px - rect.left()) / rect.width(),
            (py - rect.top()) / rect.height()
        )
        self.text_input.setGeometry(int(px), int(py), box_w, box_h)
        self.text_input.clear()
        self.text_input.show()
        self.text_input.setFocus()

    def mouseMoveEvent(self, event: QMouseEvent):
        norm = self._pos_to_normalized(event.position())
        tool = self.controller.current_tool

        if norm:
            if tool == "pointer":
                is_down = bool(event.buttons() & Qt.MouseButton.LeftButton) or self.is_pointer_down
                self.controller.update_pointer(norm[0], norm[1], True, is_down=is_down)
                self.setCursor(Qt.CursorShape.ArrowCursor)
            elif tool == "text":
                self.setCursor(Qt.CursorShape.IBeamCursor)
            elif tool == "eraser":
                self.setCursor(Qt.CursorShape.CrossCursor)
                if event.buttons() & Qt.MouseButton.LeftButton:
                    rect = self._get_page_rect()
                    aspect_ratio = rect.width() / rect.height() if rect.height() > 0 else 1.0
                    eraser_size = self.controller.get_tool_size("eraser")
                    threshold = max(0.008, eraser_size * 0.001)
                    self.controller.erase_at_point(norm[0], norm[1], threshold=threshold, aspect_ratio=aspect_ratio)
                self.hover_pos = norm
                self.update()
            elif tool in ("pen", "highlighter"):
                self.setCursor(Qt.CursorShape.CrossCursor)
                if event.buttons() & Qt.MouseButton.LeftButton:
                    if self.controller.is_line_mode:
                        snapped = self._snap_line_endpoint(norm)
                        self.controller.update_line_endpoint(snapped[0], snapped[1], pressure=1.0)
                    else:
                        self.controller.add_stroke_point(norm[0], norm[1], pressure=1.0)
                    self.hover_pos = None
                else:
                    self.hover_pos = norm
                    self.update()
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            if tool == "pointer":
                self.is_pointer_down = False
                self.controller.update_pointer(0, 0, False, is_down=False)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.hover_pos = None
            self.update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            tool = self.controller.current_tool
            if tool in ("pen", "highlighter"):
                self.controller.end_stroke()
            elif tool == "pointer":
                self.is_pointer_down = False
                norm = self._pos_to_normalized(event.position())
                if norm:
                    self.controller.update_pointer(norm[0], norm[1], True, is_down=False)
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self.controller.current_tool == "pointer":
            self.is_pointer_down = False
            self.controller.update_pointer(0, 0, False, is_down=False)
        self.hover_pos = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        super().leaveEvent(event)
