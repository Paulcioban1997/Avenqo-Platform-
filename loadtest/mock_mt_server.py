"""Isolated synthetic multi-tenant origin for Locust/k6. Binds 127.0.0.1 only.

Simulates health, session, and Central AI text without calling OpenAI/Telnyx.
Refuses to start if AVENQO_LOADTEST_BIND is not loopback.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FORBIDDEN_BIND = ("0.0.0.0", "::", "")


class MockTenantHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _tenant(self) -> str:
        return self.headers.get("X-Simulated-Company-Id") or "anonymous"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/v1/health"):
            self._send(200, {"status": "ok", "environment": "loadtest-mock", "simulated": True})
            return
        if self.path.startswith("/api/v1/auth/me"):
            cookie = self.headers.get("Cookie") or ""
            if "avenqo_access_token=" not in cookie:
                self._send(401, {"detail": "Authentification requise"})
                return
            tenant = self._tenant()
            self._send(200, {"company_id": tenant, "simulated": True})
            return
        self._send(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        if self.path.startswith("/api/v1/ai/chat"):
            tenant = self._tenant()
            message = str(body.get("message") or "ping")
            self._send(
                200,
                {
                    "status": "success",
                    "answer": f"simulated:{tenant}:{message[:80]}",
                    "provider": "mock",
                    "remaining_ai_credits": 6500,
                },
            )
            return
        if self.path.startswith("/api/v1/auth/login"):
            self.send_response(200)
            payload = json.dumps({"status": "ok", "simulated": True}).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "avenqo_access_token=simulated-token; HttpOnly; Path=/")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._send(404, {"detail": "not found"})


def serve(host: str = "127.0.0.1", port: int = 18080) -> ThreadingHTTPServer:
    if host in FORBIDDEN_BIND or host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Mock load server binds loopback only.")
    httpd = ThreadingHTTPServer((host, port), MockTenantHandler)
    httpd.allow_reuse_address = True
    return httpd


def main() -> None:
    host = os.environ.get("AVENQO_LOADTEST_BIND", "127.0.0.1")
    port = int(os.environ.get("AVENQO_LOADTEST_PORT", "18080"))
    httpd = serve(host, port)
    print(f"mock_mt_server http://{host}:{port} (simulated AI, loopback only)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
