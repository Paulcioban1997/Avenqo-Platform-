"""Railway Cron client for the protected API-side evaluation trigger."""

from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from backend.app.config.settings import get_settings


SANDBOX_ID = "e5adc24d-23b9-4275-84de-91a7801649b8"
RETRY_STATUSES = {502, 503, 504}
MAX_ATTEMPTS = 3
RETRY_WINDOW_SECONDS = 20


def _sandbox_retry_allowed(settings) -> bool:
    url = urlsplit(settings.connector_ai_scheduler_url)
    return (
        os.environ.get("RAILWAY_ENVIRONMENT_ID") == SANDBOX_ID
        and url.scheme == "https"
        and url.hostname == "avenqo-platform-sandbox.up.railway.app"
        and url.port in (None, 443)
        and url.path == "/internal/connector-ai/evaluate"
        and not (url.username or url.password or url.query or url.fragment)
    )


def _log(event, **fields):
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def run_trigger(settings, *, opener=None, sleep=None, clock=None) -> int:
    opener, sleep, clock = opener or urlopen, sleep or time.sleep, clock or time.monotonic
    if not settings.connector_ai_scheduler_url or not settings.connector_ai_scheduler_token:
        raise RuntimeError("Connector AI scheduler URL and token are required")
    request = Request(
        settings.connector_ai_scheduler_url,
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Avenqo-Scheduler-Token": settings.connector_ai_scheduler_token,
        },
        method="POST",
    )
    retry_allowed = _sandbox_retry_allowed(settings)
    deadline = clock() + RETRY_WINDOW_SECONDS
    for attempt in range(1, (MAX_ATTEMPTS if retry_allowed else 1) + 1):
        if retry_allowed and attempt > 1 and clock() >= deadline:
            _log("connector_ai_trigger_failed", attempt=attempt, reason="retry_window_exhausted", retry=False)
            return 1
        try:
            # Only this leased evaluation trigger may be retried. Never a generic
            # POST, timeout, malformed success, authorization error or other URL.
            timeout = 60 if attempt == 1 or not retry_allowed else max(0.1, deadline - clock())
            with opener(request, timeout=timeout) as response:
                payload = json.loads(response.read(16384).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Invalid scheduler response")
            claimed = payload.get("claimed")
            if type(claimed) is not int or claimed < 0:
                raise ValueError("Invalid scheduler response")
            _log("connector_ai_trigger_completed", attempt=attempt, claimed=claimed)
            return 0
        except HTTPError as exc:
            status = exc.code
            exc.close()
            delay = 2 ** (attempt - 1)
            if (not retry_allowed or status not in RETRY_STATUSES or attempt == MAX_ATTEMPTS
                    or clock() + delay >= deadline):
                _log("connector_ai_trigger_failed", attempt=attempt, http_status=status, retry=False)
                return 1
            _log("connector_ai_trigger_retry", attempt=attempt, http_status=status, backoff_seconds=delay)
            sleep(delay)
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            # Outcome can be ambiguous: leave recovery to the durable queue and
            # the next five-minute run. Never print exception text/headers/body.
            _log("connector_ai_trigger_failed", attempt=attempt, error_class=type(exc).__name__, retry=False)
            return 1
    return 1


def main() -> int:
    return run_trigger(get_settings())


if __name__ == "__main__":
    raise SystemExit(main())
