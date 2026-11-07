"""Railway Cron client for the protected API-side evaluation trigger."""

from __future__ import annotations

import logging
from backend.app.config.settings import get_settings
from backend.app.services.scheduler_http import post_scheduler_json

logger = logging.getLogger(__name__)


def main() -> int:
    settings = get_settings()
    token = settings.connector_ai_scheduler_token or ""
    url = settings.connector_ai_scheduler_url or ""

    if (
        token in {"DISABLED_BY_AUDIT", "disabled"}
        or "disabled" in url.lower()
        or (settings.environment in {"sandbox", "staging"} and not url.startswith("http"))
    ):
        print("Connector AI evaluation trigger is disabled. Exiting cleanly (exit 0).")
        return 0

    if not url or not token:
        print("Connector AI scheduler URL or token not configured. Exiting cleanly (exit 0).")
        return 0

    payload = post_scheduler_json(
        url,
        token,
        timeout=60,
    )
    claimed = int(payload.get("claimed", 0))
    print(f"Connector AI evaluation trigger completed claimed={claimed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
