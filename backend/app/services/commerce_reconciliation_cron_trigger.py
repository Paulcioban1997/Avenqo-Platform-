"""Railway Cron client for the protected commerce reconciliation trigger."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4
from backend.app.services.scheduler_http import post_scheduler_json

_IMPORTED_AT = time.monotonic()


def _event(event, **fields):
    print(json.dumps({"event": event, **fields}), flush=True)


def main() -> int:
    started, correlation = time.monotonic(), uuid4().hex
    _event("commerce_cron_started", request_id=correlation,
           started_at=datetime.now(timezone.utc).isoformat(),
           startup_seconds=round(started - _IMPORTED_AT, 3))
    phase = "configuration"
    try:
        # HTTP-only worker: no API settings, database, ML imports or credentials.
        url = os.environ.get("COMMERCE_RECONCILIATION_SCHEDULER_URL", "")
        token = os.environ.get("CONNECTOR_AI_SCHEDULER_TOKEN", "")
        target = urlsplit(url)
        if not token or target.scheme not in {"https", "http"} or not target.hostname or target.username or target.password or target.query or target.fragment or target.path != "/internal/commerce/reconcile":
            raise ValueError("Invalid scheduler configuration")
        if target.scheme == "http" and not target.hostname.endswith(".railway.internal"):
            raise ValueError("Cleartext scheduler traffic requires private networking")
        if os.environ.get("RAILWAY_ENVIRONMENT_ID") == "e5adc24d-23b9-4275-84de-91a7801649b8" and target.hostname not in {"avenqo-platform-sandbox.up.railway.app", "avenqo-platform.railway.internal"}:
            raise ValueError("Sandbox scheduler target mismatch")
        phase = "request"
        payload = post_scheduler_json(url, token, timeout=600, attempts=3,
            preconnect_retries_only=True, diagnostics=True, request_id=correlation,
            retry_window_seconds=660)
        claimed = payload.get("claimed")
        if type(claimed) is not int or claimed < 0:
            raise ValueError("Invalid scheduler response")
        _event("commerce_cron_completed", request_id=correlation, claimed=claimed,
               elapsed_seconds=round(time.monotonic() - started, 3), exit_status=0)
        print(f"Commerce reconciliation trigger completed claimed={claimed}", flush=True)
        return 0
    except Exception as exc:
        # Never print exception text, URLs, headers, response bodies or tokens.
        _event("commerce_cron_failed", request_id=correlation, category=phase, error_class=type(exc).__name__,
               elapsed_seconds=round(time.monotonic() - started, 3), exit_status=1)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
