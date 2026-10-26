"""Authenticated loopback bridge; every notebook operation executes on Qt's thread."""

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading

from PySide6.QtCore import QObject, Signal, Slot, Qt


@dataclass
class _Request:
    operation: str
    arguments: dict
    done: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cancelled: bool = False
    result: dict | None = None


class NotebookBridge(QObject):
    requested = Signal(object)

    def __init__(self, callback, connection_file, parent=None):
        super().__init__(parent)
        self.callback = callback
        self.connection_file = Path(connection_file)
        self.token = secrets.token_urlsafe(32)
        self.closed = False
        self.requested.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if (self.path != '/rpc' or self.headers.get('Origin') is not None
                        or self.headers.get('Host') != f'127.0.0.1:{bridge.server.server_port}'):
                    self._reply(403, {'error': '接続元を確認できません。'})
                    return
                auth = self.headers.get('Authorization', '')
                if not secrets.compare_digest(auth, 'Bearer ' + bridge.token):
                    self._reply(401, {'error': 'BeamerPlusへの接続認証に失敗しました。'})
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 1 <= length <= 32768:
                        raise ValueError()
                    self.connection.settimeout(5)
                    data = json.loads(self.rfile.read(length))
                    if (not isinstance(data, dict) or data.get('operation') not in
                            ('read_current_note', 'get_note_status', 'add_note_text', 'remove_note_text')
                            or not isinstance(data.get('arguments', {}), dict)):
                        raise ValueError()
                except (ValueError, OSError):
                    self._reply(400, {'error': '要求の形式が正しくありません。'})
                    return
                request = _Request(data['operation'], data.get('arguments', {}))
                bridge.requested.emit(request)
                if not request.done.wait(10):
                    # Cancel queued requests so a timed-out write cannot run later.
                    if request.lock.acquire(timeout=.1):
                        try:
                            request.cancelled = True
                        finally:
                            request.lock.release()
                        self._reply(504, {'error': 'BeamerPlusが応答しません。接続を確認してください。'})
                    else:
                        self._reply(504, {'error': '処理結果を確認できません。書き込みを再送する前にノートを読み直してください。'})
                    return
                self._reply(200, request.result)

            def _reply(self, code, result):
                raw = json.dumps(result, ensure_ascii=False).encode('utf-8')
                try:
                    self.send_response(code)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Content-Length', str(len(raw)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.connection_file.parent.mkdir(parents=True, exist_ok=True)
        self.descriptor = {'url': f'http://127.0.0.1:{self.server.server_port}/rpc', 'token': self.token}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.connection_file.parent, delete=False) as output:
                temporary = output.name
                json.dump(self.descriptor, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.connection_file)
        except Exception:
            self.server.server_close()
            raise
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.1), daemon=True)
        self.thread.start()

    @Slot(object)
    def _dispatch(self, request):
        with request.lock:
            if request.cancelled:
                return
            try:
                if self.closed:
                    raise ValueError('BeamerPlusを起動してください。')
                request.result = self.callback(request.operation, request.arguments)
            except (ValueError, TypeError, OverflowError) as exc:
                request.result = {'error': str(exc)}
            except Exception:
                request.result = {'error': 'ノートを操作できませんでした。BeamerPlusの状態を確認してください。'}
            finally:
                request.done.set()

    def stop(self):
        self.closed = True
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        try:
            if json.loads(self.connection_file.read_text()) == self.descriptor:
                self.connection_file.unlink()
        except (OSError, ValueError):
            pass
