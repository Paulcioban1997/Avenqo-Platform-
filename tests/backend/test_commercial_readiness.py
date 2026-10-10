"""Commercial catalog consistency across API source, landing copy and Flutter.

Live Stripe Checkout and Telnyx inbound audio are never treated as proven
unless the matching live credentials/flags are present.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from payments.plans import PUBLIC_PLANS, get_plan

ROOT = Path(__file__).resolve().parents[2]
WEB_TRANSLATIONS = ROOT / "web" / "src" / "lib" / "i18n" / "translations"
FLUTTER_I18N = ROOT / "frontend" / "assets" / "i18n"

CANONICAL = {
    "base": {
        "cad": 29.99,
        "usd": 21.99,
        "modules": 2,
        "credits": 6500,
        "users": 3,
        "sites": 1,
        "voice": 1,
        "calls": 1,
    },
    "professional": {
        "cad": 49.99,
        "usd": 36.99,
        "modules": 5,
        "credits": 20000,
        "users": 10,
        "sites": 3,
        "voice": 3,
        "calls": 2,
    },
}


def test_catalog_source_of_truth_matches_approved_commercial_offer():
    for code, expected in CANONICAL.items():
        plan = get_plan(code)
        assert plan.monthly_price_cad == expected["cad"]
        assert plan.monthly_price_usd == expected["usd"]
        assert plan.max_selectable_modules == expected["modules"]
        assert plan.monthly_ai_credits == expected["credits"]
        assert plan.max_users == expected["users"]
        assert plan.max_sites == expected["sites"]
        assert plan.max_voice_agents == expected["voice"]
        assert plan.max_concurrent_calls == expected["calls"]
    assert [plan.code.value for plan in PUBLIC_PLANS] == ["base", "professional", "enterprise"]


def _latin_digits(text: str) -> str:
    import unicodedata

    chars: list[str] = []
    for char in text:
        if char.isdigit():
            chars.append(str(unicodedata.digit(char)))
        elif char in " .,،٬'’":
            continue
        else:
            chars.append(char)
    return "".join(chars)


def test_web_landing_locales_advertise_canonical_quotas():
    files = sorted(path for path in WEB_TRANSLATIONS.glob("*.ts") if path.name != "trust.ts")
    assert len(files) >= 40
    checked = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        if "pricing:" not in text or "plans:" not in text:
            continue
        checked += 1
        normalized = _latin_digits(text)
        assert "6500" in normalized, path.name
        assert "20000" in normalized, path.name
    assert checked >= 40


def test_flutter_locales_use_cad_prices_and_current_credit_pack():
    files = sorted(FLUTTER_I18N.glob("*.json"))
    assert len(files) >= 40
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        pricing = data.get("pricing")
        if not isinstance(pricing, dict) or "plans" not in pricing:
            continue
        plans = pricing["plans"]
        assert "29.99" in plans[0]["priceLabel"] or "29,99" in plans[0]["priceLabel"]
        assert "49.99" in plans[1]["priceLabel"] or "49,99" in plans[1]["priceLabel"]
        assert "20,000" in plans[1]["creditAllowance"] or "20 000" in plans[1]["creditAllowance"]
        extra = plans[1]["creditExtra"]
        assert "25 USD" not in extra
        assert "$25" not in extra
        assert "pour 25" not in extra


def test_stripe_test_mode_price_is_not_claimed_without_live_key():
    key = (os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_TEST_KEY") or "").strip()
    if not key.startswith("sk_test_"):
        return
    import stripe

    stripe.api_key = key
    price_id = (os.environ.get("STRIPE_PRICE_PROFESSIONAL") or os.environ.get("STRIPE_PRICE_PRO") or "").strip()
    if not price_id:
        raise AssertionError("Stripe test key present but STRIPE_PRICE_PROFESSIONAL is missing")
    price = stripe.Price.retrieve(price_id)
    assert price.currency.lower() == "cad"
    assert price.unit_amount == 4999
    assert price.recurring and price.recurring.interval == "month"


def test_telnyx_inbound_call_is_not_claimed_without_live_proof():
    if os.environ.get("AVENQO_TELNYX_LIVE_CALL") != "1":
        from backend.app.voice.providers import unavailable_speak_payload

        french = unavailable_speak_payload("fr-CA", command_id="prep")
        assert french["language"] == "fr-CA"
        assert french["service_level"] == "premium"
        return
    raise AssertionError("AVENQO_TELNYX_LIVE_CALL=1 was set but no live inbound call evidence was recorded")
