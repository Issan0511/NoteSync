"""Passwordless access for this PC and peers verified by the local Tailscale daemon."""

import ipaddress
import json
import shutil
import subprocess
import threading
import time
from urllib.parse import urlsplit


TAILNET_V4 = ipaddress.ip_network("100.64.0.0/10")
TAILNET_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")


class ConnectionPolicy:
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def passwordless(self, host: str) -> bool:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False
        if address.is_loopback:
            return True
        if address not in TAILNET_V4 and address not in TAILNET_V6:
            return False
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(host)
            if cached and cached[0] > now:
                return cached[1]
        trusted = False
        executable = shutil.which("tailscale")
        if executable:
            try:
                result = subprocess.run([executable, "whois", "--json", host],
                                        capture_output=True, text=True, timeout=2)
                identity = json.loads(result.stdout) if result.returncode == 0 else {}
                node = identity.get("Node") or {}
                trusted = bool(node.get("ID") or node.get("StableID")) and not node.get("Expired", False)
            except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
                pass
        with self._lock:
            # Failed checks are short-lived so reconnecting Tailscale recovers quickly.
            self._cache[host] = (now + (30 if trusted else 2), trusted)
        return trusted


def websocket_origin_allowed(origin: str | None, host_header: str, http_port: int) -> bool:
    """Stop unrelated browser pages from using automatic local/Tailnet login."""
    if origin is None:
        return True  # Non-browser clients still need a verified peer or a passcode.
    try:
        page = urlsplit(origin)
        socket_host = urlsplit("//" + host_header)
        return (page.scheme in ("http", "https") and page.hostname == socket_host.hostname
                and (page.port or (443 if page.scheme == "https" else 80)) == http_port
                and not page.username and not page.password and page.path in ("", "/")
                and not page.query and not page.fragment)
    except ValueError:
        return False
