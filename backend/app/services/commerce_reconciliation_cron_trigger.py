"""Railway Cron client for the protected commerce reconciliation trigger."""

from __future__ import annotations

from backend.app.config.settings import get_settings
from backend.app.services.scheduler_http import post_scheduler_json


def main() -> int:
    settings = get_settings()
    if (
        not settings.commerce_reconciliation_scheduler_url
        or not settings.connector_ai_scheduler_token
    ):
        raise RuntimeError("Commerce reconciliation URL and scheduler token are required")
    payload = post_scheduler_json(
        settings.commerce_reconciliation_scheduler_url,
        settings.connector_ai_scheduler_token,
        timeout=600,
    )
    claimed = int(payload.get("claimed", 0))
    print(f"Commerce reconciliation trigger completed claimed={claimed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
