"""Read-only first-call diagnostics. Never places a call or enables a provider."""
from urllib.parse import urlsplit

SANDBOX_HOST = "avenqo-platform-sandbox.up.railway.app"
WEBHOOK_URL = f"https://{SANDBOX_HOST}/api/v1/voice/telnyx/webhook"
MEDIA_BASE_URL = f"wss://{SANDBOX_HOST}/api/v1/voice/telnyx/media"


def _sandbox_media_url(value: str | None) -> bool:
    try:
        url = urlsplit(value or "")
        return (
            url.scheme == "wss" and url.hostname == SANDBOX_HOST
            and url.port in (None, 443) and not url.username and not url.password
            and url.path.rstrip("/") == "/api/v1/voice/telnyx/media"
            and not url.query and not url.fragment
        )
    except ValueError:
        return False


def first_call_preflight(settings) -> dict:
    """Expose presence checks only; configuration readiness is not spend approval."""
    checks = {
        "sandbox_environment": settings.environment == "sandbox",
        "telnyx_api_key_present": bool(settings.telnyx_api_key),
        "telnyx_public_key_present": bool(settings.telnyx_public_key),
        "telnyx_connection_present": bool(settings.telnyx_voice_connection_id),
        "sandbox_wss_url": _sandbox_media_url(settings.telnyx_media_stream_base_url),
        "media_enabled": bool(settings.telnyx_media_enabled),
        "inbound_media_enabled": bool(settings.telnyx_media_inbound_enabled),
        "openai_key_present": bool(settings.openai_api_key),
        "openai_realtime_provider": settings.voice_realtime_provider == "openai",
        "realtime_model_configured": bool(settings.voice_realtime_model),
        "french_realtime_configured": "fr" in settings.voice_realtime_supported_locales,
    }
    return {
        "checks": checks,
        "configuration_status": "PASS" if all(checks.values()) else "BLOCKED",
        "call_status": "BLOCKED",
        "remaining_gates": [
            "sandbox_number_and_tenant_binding_verified",
            "provider_model_access_and_audio_handshake_verified",
            "aggregate_2_cad_ceiling_enforced_and_verified",
            "explicit_owner_paid_call_authorization",
        ],
        "retell_optional_for_telnyx_media": True,
        "calendar_sync_configured": bool(settings.google_calendar_client_id and settings.google_calendar_client_secret and settings.google_calendar_redirect_uri),
    }
