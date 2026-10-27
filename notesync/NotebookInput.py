"""Notebook input and tablet synchronization. No slideshow window dependency."""
import math
from notesync.IpadDialog import IpadDialog

class NotebookInputMixin:
    def _connect_web_signals(self):
        bindings = {
            'stroke_started': self._on_web_stroke_started,
            'stroke_moved': self._on_web_stroke_moved,
            'stroke_ended': self._on_web_stroke_ended,
            'erase_requested': self._on_web_erase_requested,
            'line_update_command': self._on_web_line_update_command,
            'page_command': self._on_web_page_command,
            'undo_requested': self._on_web_undo_requested,
            'clear_requested': self._on_web_clear_requested,
            'client_count_changed': self._on_web_client_count_changed,
            'color_command': self._on_web_color_command,
        }
        for name, handler in bindings.items(): getattr(self.web_bridge, name).connect(handler)
        for name in ('stroke_started', 'stroke_added_point', 'stroke_finished', 'strokes_cleared',
                     'stroke_undone', 'strokes_updated', 'color_changed'):
            getattr(self.controller, name).connect(getattr(self, '_sync_web_' + name))

    def _on_web_stroke_started(self, data: dict):
        self._is_handling_web_stroke = True
        tool = data.get("tool", "pen")
        color = data.get("color")
        if not color:
            color = self.controller.highlighter_color if tool == "highlighter" else self.controller.pen_color

        width_ratio = data.get("widthRatio")
        if width_ratio is None:
            size = data.get("size", 5)
            width_ratio = float(size) * 0.001

        opacity = max(0.05, min(1.0, float(data.get('opacity', self.controller.highlighter_opacity if tool == "highlighter" else self.controller.pen_opacity))))

        # PC側の current_tool や is_line_mode などの選択状態は一切変えずに直接ストロークを開始
        self.controller.begin_custom_stroke(
            color=color,
            width_ratio=float(width_ratio),
            opacity=opacity,
            norm_x=float(data["normX"]),
            norm_y=float(data["normY"]),
            pressure=max(0.0, min(1.0, float(data.get('pressure', 1.0)))),
            brush=data.get('brush', 'highlighter' if tool == 'highlighter' else 'pen') if data.get('brush', 'pen') in ('pen', 'fountain', 'pencil', 'highlighter') else 'pen'
        )

    def _on_web_stroke_moved(self, data: dict):
        self._is_handling_web_stroke = True
        self.controller.add_stroke_point(
            data["normX"],
            data["normY"],
            pressure=max(0.0, min(1.0, float(data.get('pressure', 1.0))))
        )

    def _on_web_stroke_ended(self):
        try:
            self.controller.end_stroke()
        finally:
            self._is_handling_web_stroke = False

    def _on_web_line_update_command(self, norm_x: float, norm_y: float):
        self.controller.update_line_endpoint(norm_x, norm_y, pressure=1.0)

    def _on_web_eraser_mode_command(self, mode: str):
        self.controller.set_eraser_mode(mode)

    def _on_web_line_mode_command(self, is_line: bool):
        self.controller.set_line_mode(is_line)

    def _on_web_color_command(self, tool: str, color: str):
        self.controller.set_tool_color(tool, color)

    def _on_web_undo_requested(self):
        self.controller.undo_current_page_stroke()

    def _on_web_clear_requested(self):
        self.controller.clear_current_page_strokes()

    def _on_web_client_count_changed(self, count: int):
        if hasattr(self, "btn_ipad_connect"):
            if count > 0:
                self.btn_ipad_connect.setText(f"📱 タブレット ({count})")
                self.btn_ipad_connect.setStyleSheet(
                    "QPushButton { background-color: #065f46; color: #34d399; border: 1px solid #059669; border-radius: 3px; padding: 4px 10px; font-size: 12px; font-weight: bold; }"
                )
            else:
                self.btn_ipad_connect.setText("📱 タブレット連携")
                self.btn_ipad_connect.setStyleSheet(self._tb_btn_style())

    def _sync_web_stroke_started(self, page_index: int, stroke):
        if self._is_handling_web_stroke:
            return
        if hasattr(self, "web_server") and self.web_server:
            p0 = stroke.points[0] if stroke.points else (0.0, 0.0, 1.0)
            self.web_server.broadcast({
                "type": "remote_stroke_start",
                "page": page_index,
                "color": stroke.color,
                "widthRatio": stroke.width_ratio,
                "opacity": stroke.opacity,
                "p0": [p0[0], p0[1]]
            })

    def _sync_web_stroke_added_point(self, page_index: int, norm_x: float, norm_y: float, pressure: float):
        if self._is_handling_web_stroke:
            return
        if hasattr(self, "web_server") and self.web_server:
            self.web_server.broadcast({
                "type": "remote_stroke_move",
                "page": page_index,
                "normX": norm_x,
                "normY": norm_y
            })

    def _sync_web_stroke_undone(self, index: int):
        if hasattr(self, "web_server") and self.web_server:
            status = self._get_web_status()
            target_strokes = status["sketchbookStrokes"] if self.controller.is_sketchbook else status["strokes"]
            self.web_server.broadcast({
                "type": "stroke_undone",
                "page": index,
                "strokes": target_strokes
            })

    def _sync_web_color_changed(self, tool: str, color: str):
        if hasattr(self, "web_server") and self.web_server:
            self.web_server.broadcast({
                "type": "color_changed",
                "tool": tool,
                "color": color
            })

    def show_ipad_dialog(self):
        dialog = IpadDialog(
            self.web_bridge,
            http_port=self.web_server.http_port,
            passcode=self.web_server.passcode,
            server=self.web_server,
            parent=self
        )
        dialog.exec()

    def _on_web_erase_requested(self, data: dict):
        norm_x = float(data.get("normX", 0.0))
        norm_y = float(data.get("normY", 0.0))
        mode = data.get("mode")
        size = data.get("size")
        rect = self.drawing_view.canvas._get_page_rect()
        aspect_ratio = rect.width() / rect.height() if rect.height() > 0 else 1.0
        eraser_size = int(size) if size is not None else self.controller.get_tool_size("eraser")
        threshold = max(0.008, eraser_size * 0.001)
        if 'radius' in data:
            radius = data['radius']
            if type(radius) not in (int, float) or not math.isfinite(radius) or not 0 < radius <= 8:
                return
            # Already normalized against the tablet's zoomed paper height.
            # Reapplying the legacy minimum here would enlarge a zoomed eraser.
            threshold = radius
        self.controller.erase_at_point(
            norm_x, norm_y,
            threshold=threshold,
            aspect_ratio=aspect_ratio,
            override_mode=mode
        )
