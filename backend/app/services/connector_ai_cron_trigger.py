"""Railway Cron client for the protected API-side evaluation trigger."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from backend.app.config.settings import get_settings


def main() -> int:
    settings = get_settings()
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
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    claimed = int(payload.get("claimed", 0))
    print(f"Connector AI evaluation trigger completed claimed={claimed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())