"""Railway Cron client for the protected commerce reconciliation trigger."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from backend.app.config.settings import get_settings


def main() -> int:
    settings = get_settings()
    if (
        not settings.commerce_reconciliation_scheduler_url
        or not settings.connector_ai_scheduler_token
    ):
        raise RuntimeError("Commerce reconciliation URL and scheduler token are required")
    request = Request(
        settings.commerce_reconciliation_scheduler_url,
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Avenqo-Scheduler-Token": settings.connector_ai_scheduler_token,
        },
        method="POST",
    )
    with urlopen(request, timeout=600) as response:
        payload = json.loads(response.read().decode("utf-8"))
    claimed = int(payload.get("claimed", 0))
    print(f"Commerce reconciliation trigger completed claimed={claimed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())