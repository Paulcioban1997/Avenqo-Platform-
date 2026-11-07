"""Railway Cron client for the protected commerce reconciliation trigger."""

from __future__ import annotations

import logging
from backend.app.config.settings import get_settings
from backend.app.services.scheduler_http import post_scheduler_json

logger = logging.getLogger(__name__)


def main() -> int:
    settings = get_settings()
    token = settings.connector_ai_scheduler_token or ""
    url = settings.commerce_reconciliation_scheduler_url or ""

    if (
        token in {"DISABLED_BY_AUDIT", "disabled"}
        or "disabled" in url.lower()
        or (settings.environment in {"sandbox", "staging"} and not getattr(settings, "sandbox_commerce_sync_enabled", False))
    ):
        print("Commerce reconciliation trigger is disabled in Sandbox. Exiting cleanly (exit 0).")
        return 0

    if not url or not token:
        print("Commerce reconciliation URL or scheduler token not configured. Exiting cleanly (exit 0).")
        return 0

    payload = post_scheduler_json(
        url,
        token,
        timeout=600,
    )
    claimed = int(payload.get("claimed", 0))
    print(f"Commerce reconciliation trigger completed claimed={claimed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
