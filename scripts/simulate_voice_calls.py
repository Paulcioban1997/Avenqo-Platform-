"""Create ten non-booking voice call simulations against a local Avenqo API."""

from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from uuid import uuid4

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=int, default=10)
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()
    if args.calls < 1 or args.calls > 100:
        parser.error("--calls must be between 1 and 100")

    base_url = os.environ.get("VOICE_API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
    api_key = os.environ.get("VOICE_API_KEY", "")
    agent_id = os.environ.get("VOICE_AGENT_ID", "")
    service_name = os.environ.get("VOICE_TEST_SERVICE_NAME", "")
    if not api_key or not agent_id:
        parser.error("Set VOICE_API_KEY and VOICE_AGENT_ID in the environment")
    if not args.allow_production and not any(host in base_url for host in ("127.0.0.1", "localhost", "testserver")):
        parser.error("Refusing non-local writes; pass --allow-production only for an approved test tenant")

    headers = {"X-Avenqo-Voice-Key": api_key, "Content-Type": "application/json"}
    session = requests.Session()
    info = session.post(
        f"{base_url}/voice/tools/get_business_info",
        headers=headers,
        json={"call_id": f"voice-sim-{uuid4()}", "action_id": f"voice-sim-info-{uuid4()}", "arguments": {}},
        timeout=15,
    )
    if not info.ok:
        print(f"Voice config check failed: HTTP {info.status_code}")
        return 1
    business = info.json()
    selected_service = service_name or str((business.get("services") or [{}])[0].get("name", ""))
    if not selected_service:
        print("No configured voice service is available to simulate.")
        return 1

    successes = 0
    for index in range(args.calls):
        call_id = f"voice-sim-{uuid4()}"
        action_id = f"voice-sim-info-{uuid4()}"
        info_response = session.post(
            f"{base_url}/voice/tools/get_business_info",
            headers=headers,
            json={"call_id": call_id, "action_id": action_id, "arguments": {}},
            timeout=15,
        )
        if not info_response.ok or not info_response.json().get("success"):
            print(f"Call {index + 1}: business-info tool failed (HTTP {info_response.status_code})")
            continue
        target_day = date.today() + timedelta(days=index + 1)
        availability = session.post(
            f"{base_url}/voice/tools/check_availability",
            headers=headers,
            json={
                "call_id": call_id,
                "action_id": f"voice-sim-slots-{uuid4()}",
                "arguments": {"date": target_day.isoformat(), "service_name": selected_service},
            },
            timeout=15,
        )
        if not availability.ok or not availability.json().get("success"):
            print(f"Call {index + 1}: availability tool failed (HTTP {availability.status_code})")
            continue
        ended = session.post(
            f"{base_url}/voice/retell/webhook",
            headers=headers,
            json={
                "event": "call_ended",
                "call": {
                    "call_id": call_id,
                    "agent_id": agent_id,
                    "transcript": "Simulation locale sans réservation confirmée.",
                    "call_analysis": {"call_summary": "Simulation de test; aucun rendez-vous créé."},
                },
            },
            timeout=15,
        )
        if ended.ok:
            successes += 1
            print(f"Call {index + 1}/{args.calls}: simulated; no appointment requested")
        else:
            print(f"Call {index + 1}: completion callback failed (HTTP {ended.status_code})")

    print(f"Simulation complete: {successes}/{args.calls} calls completed successfully.")
    return 0 if successes == args.calls else 1


if __name__ == "__main__":
    raise SystemExit(main())