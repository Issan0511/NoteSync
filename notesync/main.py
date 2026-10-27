import sys
import os
from PySide6.QtCore import Qt, QLoggingCategory, qInstallMessageHandler, QtMsgType
from PySide6.QtWidgets import QApplication

from notesync.NotebookWindow import NotebookWindow

# 1. QtWayland textinput などの不要な警告・デバッグログを抑制
os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.qpa.wayland*=false;qt.qpa.wayland.textinput*=false;qt.qpa.wayland.textinput.warning=false"
)

# 2. Wayland 環境で GTK ネイティブダイアログとのウィンドウハンドル不整合 (Gdk-CRITICAL) を防止
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)


def _qt_message_filter(msg_type, context, message):
    """Wayland / Gdk の偽陽性・ノイズ警告メッセージをターミナル出力から抑制"""
    if any(keyword in message for keyword in ("disableSurface", "QWaylandTextInputv3", "GDK_IS_WAYLAND_WINDOW")):
        return
    if msg_type == QtMsgType.QtFatalMsg:
        sys.stderr.write(f"Fatal: {message}\n")
        sys.exit(1)
    elif msg_type == QtMsgType.QtCriticalMsg:
        sys.stderr.write(f"Critical: {message}\n")
    elif msg_type == QtMsgType.QtWarningMsg:
        sys.stderr.write(f"Warning: {message}\n")
    elif msg_type == QtMsgType.QtInfoMsg:
        sys.stdout.write(f"Info: {message}\n")


qInstallMessageHandler(_qt_message_filter)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("NoteSync")
    main_window = NotebookWindow()
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
