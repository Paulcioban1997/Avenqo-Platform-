"""HTTP helpers for Railway cron triggers. Never log tokens or URLs with credentials."""

from __future__ import annotations

import json
import time
import socket
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_RETRYABLE_STATUS = {502, 503, 504}


def post_scheduler_json(
    url: str,
    token: str,
    *,
    timeout: int,
    attempts: int = 4,
    preconnect_retries_only: bool = False,
    diagnostics: bool = False,
    request_id: str | None = None,
    retry_window_seconds: float | None = None,
) -> dict:
    """POST JSON with retries on transient upstream errors such as a 502 during API restart."""

    payload: dict | None = None
    last_error: Exception | None = None
    started = time.monotonic()
    correlation = request_id or uuid4().hex
    if not 1 <= attempts <= 4 or timeout <= 0 or (retry_window_seconds is not None and retry_window_seconds <= 0):
        raise ValueError("Invalid scheduler request bounds")

    def emit(event, **fields):
        if diagnostics:
            print(json.dumps({"event": event, "request_id": correlation,
                "elapsed_seconds": round(time.monotonic() - started, 3), **fields}), flush=True)

    for attempt in range(attempts):
        remaining = retry_window_seconds - (time.monotonic() - started) if retry_window_seconds is not None else timeout
        if remaining <= 0:
            emit("scheduler_failed", category="retry_window_exhausted", attempt=attempt + 1)
            raise TimeoutError("Scheduler retry window exhausted") from None
        request = Request(
            url,
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "X-Avenqo-Scheduler-Token": token,
                "X-Request-ID": correlation,
            },
            method="POST",
        )
        try:
            emit("scheduler_attempt", attempt=attempt + 1, timeout_seconds=min(timeout, remaining))
            with urlopen(request, timeout=min(timeout, remaining)) as response:
                raw = response.read(16385) if diagnostics else response.read()
                if len(raw) > 16384 and diagnostics:
                    raise ValueError("Scheduler response too large")
                payload = json.loads(raw.decode("utf-8"))
            break
        except HTTPError as exc:
            last_error = exc
            emit("scheduler_failed", category="http", http_status=exc.code, attempt=attempt + 1)
            exc.close()
            # A 502/503/504 does not prove a POST was never accepted upstream.
            # Commerce has per-connection leases, not a durable request receipt.
            if preconnect_retries_only or exc.code not in _RETRYABLE_STATUS or attempt == attempts - 1:
                raise
            time.sleep(min(2 ** attempt, 8))
        except URLError as exc:
            last_error = exc
            safe = isinstance(exc.reason, (socket.gaierror, ConnectionRefusedError))
            emit("scheduler_failed", category="preconnect" if safe else "connection_outcome_unknown", attempt=attempt + 1)
            if (preconnect_retries_only and not safe) or attempt == attempts - 1:
                raise
            emit("scheduler_retry", attempt=attempt + 1, backoff_seconds=min(2 ** attempt, 8))
            time.sleep(min(2 ** attempt, 8))
        except TimeoutError:
            emit("scheduler_failed", category="timeout_outcome_unknown", attempt=attempt + 1)
            raise
    if not isinstance(payload, dict):
        raise RuntimeError("Scheduler response was not JSON object") from last_error
    return payload
