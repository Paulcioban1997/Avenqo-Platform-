"""Regression for the production incident: answer 200 -> speak 422 -> hangup, caller hears nothing."""

from __future__ import annotations

import json
import logging
import secrets
from types import SimpleNamespace

import httpx
import pytest

from backend.app.voice.providers import (
    TelnyxClient,
    unavailable_speak_attempts,
    unavailable_speak_payload,
)

API_KEY = "test-only-" + secrets.token_urlsafe(24)


def _telnyx_rules(requests: list[dict], *, reject_premium: bool = False, reject_named_voice: bool = False):
    """Mirror Telnyx validation: basic accepts only en-US + male/female; premium needs a named voice."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        requests.append({"path": request.url.path, **body})
        if request.url.path.endswith("/actions/speak"):
            if body.get("service_level") == "basic" and body.get("language") != "en-US":
                return httpx.Response(422, json={"errors": [{
                    "code": "90061", "title": "Invalid language for service level",
                    "source": {"pointer": "/language"},
                }]})
            if body.get("service_level") == "premium" and body.get("voice") in {"male", "female"}:
                return httpx.Response(422, json={"errors": [{
                    "code": "90015", "title": "Invalid voice for service level",
                    "source": {"pointer": "/voice"},
                }]})
            if reject_named_voice and str(body.get("voice", "")).startswith("Polly."):
                return httpx.Response(422, json={"errors": [{
                    "code": "90062", "title": "Voice unavailable",
                    "source": {"pointer": "/voice"},
                }]})
            if reject_premium and body.get("service_level") == "premium":
                return httpx.Response(422, json={"errors": [{"code": "90062", "title": "Voice unavailable"}]})
        return httpx.Response(200, json={"data": {"result": "ok"}})

    return handler


def _client(requests: list[dict], **rules) -> TelnyxClient:
    transport = httpx.MockTransport(_telnyx_rules(requests, **rules))
    return TelnyxClient(SimpleNamespace(telnyx_api_key=API_KEY), client=httpx.AsyncClient(transport=transport))


@pytest.mark.parametrize("locale,language,level,voice", [
    ("fr", "fr-CA", "premium", "Polly.Chantal"),
    ("fr-CA", "fr-CA", "premium", "Polly.Chantal"),
    ("fr-FR", "fr-FR", "premium", "Polly.Lea"),
    ("en", "en-US", "basic", "female"),
    ("es", "en-US", "basic", "female"),
    ("ro", "en-US", "basic", "female"),
])
def test_payload_never_combines_basic_with_non_english(locale, language, level, voice) -> None:
    payload = unavailable_speak_payload(locale, command_id="c1")
    assert (payload["language"], payload["service_level"], payload["voice"]) == (language, level, voice)
    assert payload["payload"] and payload["payload_type"] == "text"
    if level == "premium":
        assert payload["voice"] not in {"male", "female"}


def test_fallback_chain_never_retries_valid_english() -> None:
    attempts = unavailable_speak_attempts("en", command_id="c1")
    assert len(attempts) == 1
    french = unavailable_speak_attempts("fr-CA", command_id="c1")
    assert [item["language"] for item in french] == ["fr-CA", "en-US"]
    assert french[0]["voice"] == "Polly.Chantal" and french[1]["voice"] == "female"


@pytest.mark.asyncio
async def test_french_tenant_unavailable_message_is_accepted_by_telnyx_rules() -> None:
    requests: list[dict] = []
    await _client(requests).speak_unavailable("v3:call-1", command_id="cmd-1", locale="fr")
    assert len(requests) == 1
    assert requests[0]["path"] == "/v2/calls/v3:call-1/actions/speak"
    assert requests[0]["service_level"] == "premium"
    assert requests[0]["language"] == "fr-CA"
    assert requests[0]["voice"] == "Polly.Chantal"


@pytest.mark.asyncio
async def test_rejected_french_voice_falls_back_to_english_instead_of_silence(caplog) -> None:
    requests: list[dict] = []
    caplog.set_level(logging.WARNING, logger="avenqo.voice.telnyx")
    await _client(requests, reject_premium=True).speak_unavailable("v3:call-2", command_id="cmd-2", locale="fr")
    assert [(r["service_level"], r["language"], r["voice"]) for r in requests] == [
        ("premium", "fr-CA", "Polly.Chantal"),
        ("basic", "en-US", "female"),
    ]
    assert requests[0]["command_id"] != requests[1]["command_id"]
    assert "status': 422" in caplog.text and "90062" in caplog.text
    assert "/calls/{call_control_id}/actions/speak" in caplog.text
    assert "v3:call-2" not in caplog.text
    assert API_KEY not in caplog.text
    assert "indisponible" not in caplog.text


@pytest.mark.asyncio
async def test_named_voice_rejection_falls_back_instead_of_hangup_payload(caplog) -> None:
    requests: list[dict] = []
    caplog.set_level(logging.WARNING, logger="avenqo.voice.telnyx")
    await _client(requests, reject_named_voice=True).speak_unavailable("v3:call-4", command_id="cmd-4", locale="fr-CA")
    assert requests[-1]["language"] == "en-US" and requests[-1]["service_level"] == "basic"
    assert "90015" not in caplog.text or "90062" in caplog.text
    assert "v3:call-4" not in caplog.text


@pytest.mark.asyncio
async def test_english_failure_is_raised_without_retry() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(422, json={"errors": [{"code": "90018", "title": "Call has already ended"}]})

    client = TelnyxClient(SimpleNamespace(telnyx_api_key=API_KEY), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(httpx.HTTPStatusError):
        await client.speak_unavailable("v3:call-3", command_id="cmd-3", locale="en")
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_media_stream_payload_stays_credential_free() -> None:
    client = TelnyxClient(SimpleNamespace(telnyx_api_key=API_KEY, telnyx_media_enabled=True))
    payload = client.media_stream_payload(
        stream_url="wss://api.avenqo.ca/api/v1/voice/telnyx/media/11111111-1111-1111-1111-111111111111",
        client_state="state",
        command_id="media-1",
    )
    assert payload["stream_bidirectional_mode"] == "rtp"
    assert payload["stream_bidirectional_codec"] == "PCMU"
    assert "key" not in str(payload).lower()
