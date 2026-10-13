"""Prepared independent worker. Dry-run default; never deploy or run execute unapproved."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from backend.app.config.settings import get_settings
from backend.app.database import SessionLocal
from backend.app.models import VoiceCall
from backend.app.voice.providers import TelnyxClient
from backend.app.voice.sandbox_deadline import GARAGE_ID, CONFIG_ID, CONNECTION_ID, remaining_seconds, stop_expired_call


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if settings.environment != "sandbox" or settings.telnyx_voice_connection_id != CONNECTION_ID:
        raise PermissionError("Exact Sandbox configuration required")
    if os.environ.get("RAILWAY_ENVIRONMENT_ID") != "e5adc24d-23b9-4275-84de-91a7801649b8":
        raise PermissionError("Sandbox Railway environment required")
    if args.execute and os.environ.get("SANDBOX_VOICE_WATCHDOG_APPROVED") != "true":
        raise PermissionError("Separate operational approval required")
    while True:
        with SessionLocal() as db:
            calls = db.scalars(select(VoiceCall).where(
                VoiceCall.company_id == GARAGE_ID, VoiceCall.config_id == CONFIG_ID,
                VoiceCall.ended_at.is_(None))).all()
            expired = [call.id for call in calls if remaining_seconds(call.started_at) <= 0]
        if not args.execute:
            print(json.dumps({"dry_run": True, "expired_synthetic_calls": len(expired), "provider_commands": 0}))
            return
        for id in expired:
            try:
                await stop_expired_call(id, session_factory=SessionLocal,
                    settings=settings, client=TelnyxClient(settings))
            except Exception as exc:
                print(json.dumps({"stop_failed": True, "call_id": str(id), "error_class": type(exc).__name__}))
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
