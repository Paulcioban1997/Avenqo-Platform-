"""Loopback OpenAI-compatible mock. Never forwards to api.openai.com."""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class OpenAIMockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError, OSError):
            # Client disconnect during load teardown must not print to stderr.
            return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError, OSError):
            return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.endswith("/models"):
            self._json(200, {"data": [{"id": "gpt-4o-mini", "object": "model"}]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        try:
            raw = self.rfile.read(length) if length else b"{}"
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError, OSError):
            return
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        if self.path.endswith("/chat/completions"):
            messages = body.get("messages") or []
            last = ""
            for item in reversed(messages):
                if item.get("role") == "user":
                    last = str(item.get("content") or "")
                    break
            answer = f"simulated-central:{last[:120] or 'ok'}"
            time.sleep(float(os.environ.get("AVENQO_ISOLATED_LLM_HOLD_S", "0.4")))
            self._json(
                200,
                {
                    "id": "chatcmpl-isolated",
                    "object": "chat.completion",
                    "model": body.get("model") or "gpt-4o-mini",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": answer},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
                },
            )
            return
        self._json(404, {"error": {"message": "not found"}})


class _QuietThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = False

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001
        # Suppress default stderr traceback spam on client disconnect.
        return


def serve(host: str = "127.0.0.1", port: int = 18081) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("OpenAI mock binds loopback only.")
    httpd = _QuietThreadingHTTPServer((host, port), OpenAIMockHandler)
    httpd.allow_reuse_address = True
    return httpd


def start(host: str = "127.0.0.1", port: int = 18081) -> tuple[ThreadingHTTPServer, threading.Thread]:
    httpd = serve(host, port)
    thread = threading.Thread(target=httpd.serve_forever, name="avenqo-openai-mock", daemon=False)
    thread.start()
    return httpd, thread


def stop(httpd: ThreadingHTTPServer | None, thread: threading.Thread | None = None, timeout: float = 5.0) -> None:
    if httpd is None:
        return
    try:
        httpd.shutdown()
    except Exception:
        pass
    try:
        httpd.server_close()
    except Exception:
        pass
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
