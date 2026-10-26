import os
import json
import socket
import asyncio
import threading
import secrets
import string
import re
import hashlib
from typing import Callable
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkInterface, QAbstractSocket, QHostInfo
import websockets
from websockets.protocol import State
from beamerplus.Assistant import NoteAssistant, AssistantError, validate_question
from beamerplus.TabletNotebook import NOTEBOOK_HTML
from beamerplus.ConnectionPolicy import ConnectionPolicy, websocket_origin_allowed


def generate_passcode(length: int = 8) -> str:
    """判読しやすく手入力しやすい英数字によるランダムパスコードを生成（英大文字・小文字・数字）"""
    # 紛らわしい文字 (0, O, 1, I, l) を除いた英数字セット
    alphabet = "23456789abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_local_ip() -> str:
    """LAN内のローカルIPアドレスを取得"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # ルーティング可能なIPを取得（実際に通信は発生しない）
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def get_network_interfaces() -> list[dict]:
    """
    接続可能なネットワークインターフェースのIPアドレスおよびホスト名の一覧を取得する。
    戻り値: [{'display': '...', 'host': '...', 'is_default': bool}, ...]
    """
    primary_ip = get_local_ip()
    hostname = ""
    try:
        hostname = QHostInfo.localHostName()
    except Exception:
        pass
    if not hostname:
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = ""

    valid_interfaces: list[tuple[str, str]] = []
    loopback_interfaces: list[tuple[str, str]] = []

    try:
        for iface in QNetworkInterface.allInterfaces():
            flags = iface.flags()
            # 停止中のインターフェースは除外
            if not (flags & QNetworkInterface.InterfaceFlag.IsUp):
                continue

            is_loopback = bool(flags & QNetworkInterface.InterfaceFlag.IsLoopBack)
            raw_name = iface.humanReadableName() or iface.name()
            name = raw_name.strip()

            for entry in iface.addressEntries():
                ip = entry.ip()
                if ip.protocol() != QAbstractSocket.NetworkLayerProtocol.IPv4Protocol:
                    continue
                ip_str = ip.toString().strip()
                if not ip_str or ip_str == "0.0.0.0":
                    continue

                if is_loopback or ip_str == "127.0.0.1":
                    loopback_interfaces.append((ip_str, name))
                else:
                    valid_interfaces.append((ip_str, name))
    except Exception as e:
        print(f"[BeamerPlus] Error detecting network interfaces: {e}")

    # primary_ip が取得できたが valid_interfaces に入っていない場合は追加
    if primary_ip != "127.0.0.1" and not any(ip == primary_ip for ip, _ in valid_interfaces):
        valid_interfaces.insert(0, (primary_ip, "LAN"))

    results: list[dict] = []
    seen_hosts: set[str] = set()

    # 1. プライマリ（同じLAN向け）IPアドレス
    for ip_str, name in valid_interfaces:
        if ip_str == primary_ip:
            if "tailscale" in name.casefold():
                label = f"{ip_str} (Tailscale / Tailnet)"
            else:
                label = f"{ip_str} (同じLAN: {name})" if name else f"{ip_str} (同じLAN)"
            results.append({"display": label, "host": ip_str, "is_default": True})
            seen_hosts.add(ip_str)
            break

    # 2. ドメイン / デバイス名 (mDNS: .local)
    clean_host = hostname.strip()
    if clean_host and clean_host.lower() not in ("localhost", "127.0.0.1", "0.0.0.0"):
        if "." in clean_host:
            mdns_host = clean_host
        else:
            mdns_host = f"{clean_host}.local"

        if mdns_host not in seen_hosts:
            results.append({
                "display": f"{mdns_host} (デバイス名)",
                "host": mdns_host,
                "is_default": False
            })
            seen_hosts.add(mdns_host)

    # 3. その他の有効なインターフェース
    for ip_str, name in valid_interfaces:
        if ip_str in seen_hosts:
            continue
        if "tailscale" in name.casefold():
            label = f"{ip_str} (Tailscale / Tailnet)"
        else:
            label = f"{ip_str} ({name})" if name else ip_str
        results.append({"display": label, "host": ip_str, "is_default": False})
        seen_hosts.add(ip_str)

    # 4. ループバック (ローカルホスト)
    for ip_str, name in loopback_interfaces:
        if ip_str in seen_hosts:
            continue
        results.append({
            "display": f"{ip_str} (ローカル)",
            "host": ip_str,
            "is_default": False
        })
        seen_hosts.add(ip_str)

    # 何も取れなかった場合のフォールバック
    if not results:
        results.append({
            "display": "127.0.0.1 (ローカル)",
            "host": "127.0.0.1",
            "is_default": True
        })

    # A stable Tailnet address is preferable when Tailscale is available.
    tailnet_entries = [entry for entry in results if "Tailscale / Tailnet" in entry["display"]]
    if tailnet_entries:
        results = tailnet_entries + [entry for entry in results if entry not in tailnet_entries]
        for index, entry in enumerate(results):
            entry["is_default"] = index == 0

    # is_default がどれにも設定されていない場合は先頭をデフォルトにする
    if not any(r["is_default"] for r in results):
        results[0]["is_default"] = True

    return results


# --- iPad向け Web アプリケーション (HTML / CSS / JavaScript) ---
HTML_CONTENT = NOTEBOOK_HTML
CLIENT_BUILD = hashlib.sha256(HTML_CONTENT.encode()).hexdigest()[:16]


# --- Qt シグナルブリッジ ---
class WebBridge(QObject):
    stroke_started = Signal(dict)
    stroke_moved = Signal(dict)
    stroke_ended = Signal()
    pointer_updated = Signal(float, float, bool, bool)
    erase_requested = Signal(dict)
    eraser_mode_command = Signal(str)  # "partial" または "stroke"
    line_mode_command = Signal(bool)    # 直線モード ON/OFF
    line_update_command = Signal(float, float) # 直線終点更新
    page_command = Signal(str, int)  # "next", "prev", "set", page_idx
    tool_command = Signal(str)
    tool_size_command = Signal(str, int)
    color_command = Signal(str, str)
    undo_requested = Signal()
    clear_requested = Signal()
    client_count_changed = Signal(int)
    blank_command = Signal(bool)
    sketchbook_command = Signal(bool)
    toggle_blank_command = Signal()
    toggle_sketchbook_command = Signal()
    sketch_visibility_command = Signal(bool)
    toggle_sketch_visibility_command = Signal()
    save_sketch_requested = Signal()
    notebook_command = Signal(dict)
    erase_started = Signal()
    erase_ended = Signal()
    redo_requested = Signal()


# --- HTTP リクエストハンドラ ---
class SlideRequestHandler(SimpleHTTPRequestHandler):
    image_provider: Callable[[int], bytes | None] | None = None
    status_provider: Callable[[], dict] | None = None
    ws_port: int = 8765
    passcode: str = ""
    connection_policy: ConnectionPolicy | None = None

    def end_headers(self):
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        super().end_headers()

    def _passwordless(self):
        policy = SlideRequestHandler.connection_policy
        return bool(policy and policy.passwordless(self.client_address[0]))

    def _authorized(self, params):
        return self._passwordless() or (bool(SlideRequestHandler.passcode)
                and params.get("code", [""])[0] == SlideRequestHandler.passcode)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            content = HTML_CONTENT.replace("__WS_PORT__", str(SlideRequestHandler.ws_port))
            content = content.replace("__AUTO_AUTH__", "true" if self._passwordless() else "false")
            content = content.replace("__CLIENT_BUILD__", CLIENT_BUILD)
            self.wfile.write(content.encode("utf-8"))
            return

        elif path == "/api/slide":
            if not self._authorized(params):
                self.send_response(401)
                self.end_headers()
                return

            page_str = params.get("page", ["0"])[0]
            try:
                page_idx = int(page_str)
            except ValueError:
                page_idx = 0

            image_data = None
            if SlideRequestHandler.image_provider:
                image_data = SlideRequestHandler.image_provider(page_idx)

            if image_data:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(image_data)
            else:
                self.send_response(404)
                self.end_headers()
            return

        elif path == "/api/status":
            if not self._authorized(params):
                self.send_response(401)
                self.end_headers()
                return

            status = {}
            if SlideRequestHandler.status_provider:
                status = SlideRequestHandler.status_provider()
            res = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res)
            return

        # Only serve the tablet app and its authenticated endpoints, never local files.
        self.send_error(404)

    def log_message(self, format, *args):
        pass  # ターミナルログ抑制


# --- WebServer 統合クラス ---
class WebServer:
    def __init__(
        self,
        bridge: WebBridge,
        image_provider: Callable[[int], bytes | None],
        status_provider: Callable[[], dict],
        http_port: int = 8080,
        ws_port: int = 8765,
        passcode: str | None = None,
    ):
        self.bridge = bridge
        self.image_provider = image_provider
        self.status_provider = status_provider
        self.http_port = http_port
        self.ws_port = ws_port
        self.passcode = str(passcode) if passcode else generate_passcode(8)

        SlideRequestHandler.image_provider = staticmethod(self.image_provider)
        SlideRequestHandler.status_provider = staticmethod(self.status_provider)
        SlideRequestHandler.passcode = self.passcode

        self.http_server: ThreadingHTTPServer | None = None
        self.http_thread: threading.Thread | None = None
        self.ws_thread: threading.Thread | None = None
        self.ws_loop: asyncio.AbstractEventLoop | None = None
        self.connected_clients: set = set()
        self.is_running: bool = False
        self.assistant = NoteAssistant()
        self.connection_policy = ConnectionPolicy()
        SlideRequestHandler.connection_policy = self.connection_policy

    def is_passwordless_host(self, host: str) -> bool:
        return self.connection_policy.passwordless(host)

    def set_passcode(self, new_passcode: str):
        """iPad 接続用パスコードを更新"""
        self.passcode = str(new_passcode).strip()
        SlideRequestHandler.passcode = self.passcode

    def start(self):
        if self.is_running:
            return
        self.is_running = True

        # 1. HTTP サーバー起動
        def run_http():
            ThreadingHTTPServer.allow_reuse_address = True
            for port in range(self.http_port, self.http_port + 10):
                try:
                    self.http_server = ThreadingHTTPServer(("0.0.0.0", port), SlideRequestHandler)
                    self.http_port = port
                    self.http_server.serve_forever()
                    break
                except OSError as e:
                    if port == self.http_port + 9:
                        print(f"[BeamerPlus] HTTP Server Error: {e}")

        self.http_thread = threading.Thread(target=run_http, daemon=True)
        self.http_thread.start()

        # 2. WebSocket サーバー起動
        def run_ws():
            self.ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.ws_loop)

            async def ws_handler(websocket):
                authenticated = False
                ai_task = None
                ai_cancelled = threading.Event()
                ai_session = {"context": None, "history": []}
                try:
                    headers = getattr(getattr(websocket, "request", None), "headers", None)
                    if headers is None:
                        headers = getattr(websocket, "request_headers", {})
                    if not websocket_origin_allowed(headers.get("Origin"), headers.get("Host", ""), self.http_port):
                        await websocket.close(code=1008, reason="接続元のページを確認できません")
                        return
                    peer_host = websocket.remote_address[0] if websocket.remote_address else ""
                    passwordless = await asyncio.to_thread(self.connection_policy.passwordless, peer_host)
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                        except Exception:
                            continue

                        if not isinstance(data, dict):
                            continue
                        msg_type = data.get("type")

                        if not authenticated:
                            if msg_type == "auth":
                                req_code = str(data.get("passcode", "")).strip()
                                if passwordless or (bool(self.passcode) and req_code == self.passcode):
                                    authenticated = True
                                    self.connected_clients.add(websocket)
                                    self.bridge.client_count_changed.emit(len(self.connected_clients))

                                    await websocket.send(json.dumps({
                                        "type": "auth_result",
                                        "success": True, "clientBuild": CLIENT_BUILD
                                    }))

                                    # 初期状態送信
                                    try:
                                        init_data = self.status_provider()
                                        init_data["type"] = "state_sync"
                                        await websocket.send(json.dumps(init_data))
                                    except Exception:
                                        pass
                                    await websocket.send(json.dumps({
                                        "type": "ai_status", "configured": self.assistant.configured,
                                        "model": self.assistant.model,
                                    }))
                                    if not data.get('clientBuild'):
                                        await websocket.send(json.dumps({
                                            'type': 'note_error',
                                            'message': '画面が更新されています。GPTの書き込み・数式を表示するには、タブレットのページを一度再読み込みしてください。',
                                        }))
                                else:
                                    await websocket.send(json.dumps({
                                        "type": "auth_result",
                                        "success": False,
                                        "message": "パスコードが正しくありません"
                                    }))
                            continue

                        if msg_type == "ai_ask":
                            request_id = data.get("requestId", "")
                            if not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", request_id):
                                continue
                            if ai_task and not ai_task.done():
                                await websocket.send(json.dumps({
                                    "type": "ai_error", "requestId": request_id,
                                    "message": "前の質問に回答中です。少し待ってください。",
                                }))
                                continue
                            ai_cancelled = threading.Event()
                            ai_task = asyncio.create_task(self._respond_to_ai(websocket, data, ai_session, ai_cancelled))
                        elif msg_type == "ai_reset":
                            if not ai_task or ai_task.done():
                                ai_session.update(context=None, history=[])
                        else:
                            self._handle_client_message(data, websocket)

                except (websockets.exceptions.ConnectionClosed, ConnectionResetError, BrokenPipeError):
                    pass
                except Exception:
                    pass
                finally:
                    ai_cancelled.set()
                    if ai_task and not ai_task.done():
                        ai_task.cancel()
                    if authenticated:
                        self.connected_clients.discard(websocket)
                        self.bridge.client_count_changed.emit(len(self.connected_clients))

            async def main_ws():
                for port in range(self.ws_port, self.ws_port + 10):
                    try:
                        async with websockets.serve(ws_handler, "0.0.0.0", port, max_size=16 * 1024 * 1024):
                            self.ws_port = port
                            SlideRequestHandler.ws_port = port
                            await asyncio.Future()
                        break
                    except OSError:
                        if port == self.ws_port + 9:
                            raise

            try:
                self.ws_loop.run_until_complete(main_ws())
            except Exception as e:
                print(f"[BeamerPlus] WebSocket Server Error: {e}")

        self.ws_thread = threading.Thread(target=run_ws, daemon=True)
        self.ws_thread.start()

    async def _respond_to_ai(self, websocket, data, session, cancelled):
        """Stream only to the requester; keep network work off Qt and WS threads."""
        request_id = data["requestId"]
        loop = asyncio.get_running_loop()

        def emit(delta):
            if cancelled.is_set():
                return
            future = asyncio.run_coroutine_threadsafe(websocket.send(json.dumps({
                "type": "ai_delta", "requestId": request_id, "delta": delta,
            })), loop)
            try:
                future.result(timeout=5)
            except Exception:
                cancelled.set()

        try:
            question, context, image = validate_question(data)
            history = list(session["history"]) if session["context"] == context else []
            answer = await asyncio.to_thread(self.assistant.stream, question, image, history, emit, cancelled)
            if cancelled.is_set():
                return
            session.update(context=context, history=(history + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer[:16000]},
            ])[-12:])
            await websocket.send(json.dumps({"type": "ai_done", "requestId": request_id}))
        except AssistantError as exc:
            await websocket.send(json.dumps({"type": "ai_error", "requestId": request_id, "message": str(exc)}))
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except websockets.exceptions.ConnectionClosed:
            cancelled.set()
        except Exception:
            await websocket.send(json.dumps({
                "type": "ai_error", "requestId": request_id,
                "message": "回答の取得に失敗しました。再接続してお試しください。",
            }))

    def _handle_client_message(self, data: dict, reply_client=None):
        msg_type = data.get("type")
        if msg_type == 'note_file':
            payload = dict(data)
            payload['_reply_client'] = reply_client
            self.bridge.notebook_command.emit(payload)
        elif msg_type in ('note_new', 'note_select', 'note_title', 'note_paper', 'note_save', 'note_ink_edit', 'note_library', 'note_save_checkpoint'):
            self.bridge.notebook_command.emit(data)
        elif msg_type == 'erase_start':
            self.bridge.erase_started.emit()
        elif msg_type == 'erase_end':
            self.bridge.erase_ended.emit()
        elif msg_type == 'redo':
            self.bridge.redo_requested.emit()
        elif msg_type == "stroke_start":
            self.bridge.stroke_started.emit(data)
        elif msg_type == "stroke_move":
            self.bridge.stroke_moved.emit(data)
        elif msg_type == "stroke_end":
            self.bridge.stroke_ended.emit()
        elif msg_type == "pointer_move":
            self.bridge.pointer_updated.emit(
                float(data.get("normX", 0.0)),
                float(data.get("normY", 0.0)),
                bool(data.get("visible", False)),
                bool(data.get("isDown", False))
            )
        elif msg_type == "erase":
            self.bridge.erase_requested.emit(data)
        elif msg_type == "set_eraser_mode":
            self.bridge.eraser_mode_command.emit(str(data.get("mode", "partial")))
        elif msg_type == "set_line_mode":
            self.bridge.line_mode_command.emit(bool(data.get("isLine", False)))
        elif msg_type == "line_update":
            self.bridge.line_update_command.emit(
                float(data.get("normX", 0.0)),
                float(data.get("normY", 0.0))
            )
        elif msg_type == "prev_page":
            self.bridge.page_command.emit("prev", 0)
        elif msg_type == "next_page":
            self.bridge.page_command.emit("next", 0)
        elif msg_type == "set_page":
            self.bridge.page_command.emit("set", int(data.get("page", 0)))
        elif msg_type == "set_tool":
            self.bridge.tool_command.emit(str(data.get("tool", "pen")))
        elif msg_type == "set_tool_size":
            self.bridge.tool_size_command.emit(
                str(data.get("tool", "pen")),
                int(data.get("size", 5))
            )
        elif msg_type == "set_color":
            self.bridge.color_command.emit(
                str(data.get("tool", "pen")),
                str(data.get("color", "#e53935"))
            )
        elif msg_type == "undo":
            self.bridge.undo_requested.emit()
        elif msg_type == "clear":
            self.bridge.clear_requested.emit()
        elif msg_type == "toggle_blank":
            self.bridge.toggle_blank_command.emit()
        elif msg_type == "set_blank":
            self.bridge.blank_command.emit(bool(data.get("enabled", False)))
        elif msg_type == "toggle_sketchbook":
            self.bridge.toggle_sketchbook_command.emit()
        elif msg_type == "set_sketchbook":
            self.bridge.sketchbook_command.emit(bool(data.get("enabled", False)))
        elif msg_type == "toggle_sketch_visibility":
            self.bridge.toggle_sketch_visibility_command.emit()
        elif msg_type == "set_sketch_visibility":
            self.bridge.sketch_visibility_command.emit(bool(data.get("visible", True)))
        elif msg_type == "save_sketch":
            self.bridge.save_sketch_requested.emit()

    def reply_to(self, client, message_dict: dict):
        """Return a download to its requesting device, never broadcast files."""
        if client is None or not self.ws_loop:
            return
        payload = json.dumps(message_dict)

        async def _send():
            if client.state == State.OPEN:
                try:
                    await client.send(payload)
                except (websockets.exceptions.ConnectionClosed, ConnectionResetError):
                    pass

        asyncio.run_coroutine_threadsafe(_send(), self.ws_loop)

    def broadcast(self, message_dict: dict):
        """全接続クライアント（iPad）へメッセージをブロードキャスト"""
        if not self.connected_clients or not self.ws_loop:
            return

        payload = json.dumps(message_dict)

        async def _send():
            tasks = []
            for ws in list(self.connected_clients):
                if ws.state == State.OPEN:
                    tasks.append(ws.send(payload))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        asyncio.run_coroutine_threadsafe(_send(), self.ws_loop)

    def stop(self):
        if self.http_server:
            self.http_server.shutdown()
        if self.ws_loop:
            self.ws_loop.stop()
        self.is_running = False
