"""HTTP helpers for Railway cron triggers. Never log tokens or URLs with credentials."""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_RETRYABLE_STATUS = {502, 503, 504}


def post_scheduler_json(
    url: str,
    token: str,
    *,
    timeout: int,
    attempts: int = 4,
) -> dict:
    """POST JSON with retries on transient upstream errors such as a 502 during API restart."""

    payload: dict | None = None
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = Request(
            url,
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "X-Avenqo-Scheduler-Token": token,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as exc:
            last_error = exc
            if exc.code not in _RETRYABLE_STATUS or attempt == attempts - 1:
                raise
            time.sleep(min(2 ** attempt, 8))
        except URLError as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
            time.sleep(min(2 ** attempt, 8))
    if not isinstance(payload, dict):
        raise RuntimeError("Scheduler response was not JSON object") from last_error
    return payload
