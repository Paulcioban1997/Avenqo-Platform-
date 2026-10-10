"""Read-only provider authentication evidence; never prints credentials or response bodies.

Run inside the authorized runtime. This does not establish webhook delivery,
successful payment, audible Voice conversation or calendar scheduling.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-environment", required=True)
    args = parser.parse_args(argv)
    try:
        import requests
        from backend.app.config.settings import get_settings

        settings = get_settings()
        if settings.environment != args.confirm_environment:
            print("Environment mismatch; no requests made.", file=sys.stderr)
            return 2
        results = {}
        specs = (
            ("stripe", settings.stripe_secret_key, "https://api.stripe.com/v1/account"),
            ("telnyx", settings.telnyx_api_key, "https://api.telnyx.com/v2/phone_numbers?page[size]=1"),
        )
        for provider, key, url in specs:
            if not key:
                results[provider] = {"state":"missing_configuration"}
                continue
            if provider == "stripe" and settings.environment in {"test","sandbox"} and key.startswith(("sk_live_","rk_live_")):
                results[provider] = {"state":"blocked_live_key_in_test_environment"}
                continue
            try:
                response = requests.get(url, headers={"Authorization":"Bearer "+key}, timeout=20, allow_redirects=False)
                results[provider] = {"state":"read_only_success" if response.status_code==200 else "read_only_failure", "http_status":response.status_code}
            except Exception:
                results[provider] = {"state":"request_unverified"}
        print(json.dumps({"environment":settings.environment,"read_only":True,"no_payment_or_call_created":True,"results":results}))
        return 0 if all(r["state"]=="read_only_success" for r in results.values()) else 1
    except Exception:
        print("Read-only readiness check unavailable; sensitive details withheld.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
