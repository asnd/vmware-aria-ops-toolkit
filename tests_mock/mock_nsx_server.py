"""In-process mock NSX Policy API server for contract-testing Robot keyword wiring.

The unit tests under tests_unit/ only exercise pure-Python logic (nsxt_robot.api,
nsxt_robot.bbprobe_release) — they cannot verify that a keyword like ``Create T1
Gateway`` in policy_api.robot actually builds the right HTTP method/path/JSON body,
since that construction happens in Robot syntax (``Create Dictionary`` etc.), not
Python. This module is a tiny stdlib-only HTTP server that records every request it
receives and echoes PATCH/PUT bodies back on a matching GET (mirroring how NSX's
Policy API returns the object you just wrote), so a real ``robot`` run against it can
assert on exactly what a keyword sent — without needing a live NSX Manager.

Dev/test-only: not part of the published nsxt_robot package.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from robot.api.deco import keyword, library


class _Handler(BaseHTTPRequestHandler):
    def _read_body(self) -> Any:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        raw = self.rfile.read(length)
        return json.loads(raw) if raw else None

    def _send_json(self, status: int, body: Any) -> None:
        payload = json.dumps(body if body is not None else {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _record(self, method: str) -> Any:
        body = self._read_body()
        self.server.requests.append({"method": method, "path": self.path, "body": body})
        return body

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        self.server.requests.append({"method": "GET", "path": self.path, "body": None})
        clean_path = self.path.split("?", 1)[0]
        if "/realized-state/status" in clean_path:
            self._send_json(200, {"consolidated_status": {"consolidated_status": "SUCCESS"}})
            return
        stored = self.server.objects.get(clean_path)
        if stored is not None:
            self._send_json(200, stored)
        else:
            self._send_json(404, {"error_message": f"not found: {clean_path}"})

    def do_PATCH(self) -> None:  # noqa: N802
        body = self._record("PATCH")
        self.server.objects[self.path.split("?", 1)[0]] = body
        self._send_json(200, body if body is not None else {})

    def do_PUT(self) -> None:  # noqa: N802
        self.do_PATCH()

    def do_POST(self) -> None:  # noqa: N802
        body = self._record("POST")
        self._send_json(202, body if body is not None else {})

    def do_DELETE(self) -> None:  # noqa: N802
        self._record("DELETE")
        self.server.objects.pop(self.path.split("?", 1)[0], None)
        self._send_json(200, {})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # silence default request logging to stderr


class _MockServer(ThreadingHTTPServer):
    requests: list
    objects: dict


@library(scope="GLOBAL", auto_keywords=False)
class MockNsxServer:
    """Start/stop an in-process mock NSX Policy API server and inspect what it received."""

    ROBOT_LIBRARY_VERSION = "1.0.0"

    def __init__(self) -> None:
        self._server: _MockServer | None = None
        self._thread: threading.Thread | None = None

    @keyword("Start Mock NSX Server")
    def start(self, port: int = 0) -> int:
        """Start the mock server on ``port`` (0 = OS-assigned) and return the port used."""
        server = _MockServer(("127.0.0.1", int(port)), _Handler)
        server.requests = []
        server.objects = {}
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        return server.server_address[1]

    @keyword("Stop Mock NSX Server")
    def stop(self) -> None:
        """Stop the mock server, if running."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @keyword("Get Mock NSX Requests")
    def get_requests(self) -> list:
        """Return every request the mock server has received so far, in order."""
        if self._server is None:
            return []
        return list(self._server.requests)

    @keyword("Get Mock NSX Last Request")
    def get_last_request(self) -> dict:
        """Return the most recently received request (method/path/body)."""
        requests = self.get_requests()
        if not requests:
            raise AssertionError("No requests recorded by the mock NSX server")
        return requests[-1]

    @keyword("Reset Mock NSX Requests")
    def reset(self) -> None:
        """Clear recorded requests (not stored objects) between test cases."""
        if self._server is not None:
            self._server.requests = []
