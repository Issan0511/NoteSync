"""Optional extensions. NoteSync itself never owns model credentials or requests.

An entry point in ``notesync.extensions`` supplies ``tablet_assets()``,
``attach_window(host)`` and ``connection(server, websocket)``. Its package owns
its controls, network requests, per-client session and shutdown behavior.
"""
from functools import lru_cache
from importlib.metadata import entry_points
import logging
import os

@lru_cache(maxsize=1)
def _installed():
    result = []
    for entry in entry_points(group='notesync.extensions'):
        try:
            result.append(entry.load()())
        except Exception:
            logging.getLogger(__name__).exception('Could not load extension %s', entry.name)
    return tuple(result)

def extensions():
    return () if os.environ.get('NOTESYNC_DISABLE_EXTENSIONS') == '1' else _installed()

def tablet_assets():
    parts = [extension.tablet_assets() for extension in extensions()]
    # Isolate extension globals; fan out connection events and stop at the first handler.
    scripts = ["(() => {\n" + part[2] + "\nreturn {connected: updateExtensionConnection, handle: handleExtensionMessage};})()"
               for part in parts]
    script = ('const notebookExtensions = [' + ',\n'.join(scripts) + '];\n'
              'function updateExtensionConnection(connected){notebookExtensions.forEach(ext=>ext.connected(connected));}\n'
              'function handleExtensionMessage(message){return notebookExtensions.some(ext=>ext.handle(message));}')
    return '\n'.join(part[0] for part in parts), '\n'.join(part[1] for part in parts), script

class ExtensionHost:
    """Version-1 extension API. All window callbacks execute on the Qt thread."""
    api_version = 1
    def __init__(self, window):
        self.parent = window
        self.operations = {}

    def metadata(self): return self.parent._mcp_metadata()
    def snapshot(self): return self.metadata(), self.parent.controller.serialized_ink()
    def on_ink_change(self, callback):
        for name in ('stroke_started', 'stroke_added_point', 'stroke_line_updated', 'stroke_finished',
                     'strokes_updated', 'strokes_cleared', 'texts_updated'):
            getattr(self.parent.controller, name).connect(callback)
    def add_action(self, label, callback):
        from PySide6.QtWidgets import QPushButton
        button = QPushButton(label)
        button.clicked.connect(callback)
        self.parent.main_toolbar.addWidget(button)
        return button
    def add_toolbar(self, title):
        from PySide6.QtWidgets import QToolBar
        bar = QToolBar(title, self.parent)
        bar.setMovable(False)
        self.parent.addToolBarBreak()
        self.parent.addToolBar(bar)
        return bar
    def register_operation(self, name, callback):
        if name in self.operations: raise ValueError('Duplicate extension operation')
        self.operations[name] = callback
    def broadcast(self, message): self.parent.web_server.broadcast(message)


def extension_instructions():
    return '\n'.join(extension.mcp_instructions() for extension in extensions()
                     if hasattr(extension, 'mcp_instructions'))
