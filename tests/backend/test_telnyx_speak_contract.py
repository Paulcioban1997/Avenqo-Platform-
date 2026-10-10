"""Regression for the production incident: answer 200 -> speak 422 -> hangup, caller hears nothing."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import httpx
import pytest

from backend.app.voice.providers import TelnyxClient, unavailable_speak_payload

API_KEY = "KEY-test-secret-never-log"


def _telnyx_rules(requests: list[dict], *, reject_premium: bool = False):
    """Mirror Telnyx validation: service_level=basic only accepts language en-US."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        requests.append({"path": request.url.path, **body})
        if body.get("service_level") == "basic" and body.get("language") != "en-US":
            return httpx.Response(422, json={"errors": [{
                "code": "90061", "title": "Invalid language for service level",
                "source": {"pointer": "/language"},
            }]})
        if reject_premium and body.get("service_level") == "premium":
            return httpx.Response(422, json={"errors": [{"code": "90062", "title": "Voice unavailable"}]})
        return httpx.Response(200, json={"data": {"result": "ok"}})

    return handler


def _client(requests: list[dict], **rules) -> TelnyxClient:
    transport = httpx.MockTransport(_telnyx_rules(requests, **rules))
    return TelnyxClient(SimpleNamespace(telnyx_api_key=API_KEY), client=httpx.AsyncClient(transport=transport))


@pytest.mark.parametrize("locale,language,level", [
    ("fr", "fr-CA", "premium"), ("fr-CA", "fr-CA", "premium"), ("fr-FR", "fr-FR", "premium"),
    ("en", "en-US", "basic"), ("es", "en-US", "basic"), ("ro", "en-US", "basic"),
])
def test_payload_never_combines_basic_with_non_english(locale, language, level) -> None:
    payload = unavailable_speak_payload(locale, command_id="c1")
    assert (payload["language"], payload["service_level"]) == (language, level)
    assert payload["voice"] and payload["payload"] and payload["payload_type"] == "text"


@pytest.mark.asyncio
async def test_french_tenant_unavailable_message_is_accepted_by_telnyx_rules() -> None:
    requests: list[dict] = []
    await _client(requests).speak_unavailable("v3:call-1", command_id="cmd-1", locale="fr")
    assert len(requests) == 1
    assert requests[0]["path"] == "/v2/calls/v3:call-1/actions/speak"
    assert requests[0]["service_level"] == "premium" and requests[0]["language"] == "fr-CA"


@pytest.mark.asyncio
async def test_rejected_french_voice_falls_back_to_english_instead_of_silence(caplog) -> None:
    requests: list[dict] = []
    caplog.set_level(logging.WARNING, logger="avenqo.voice.telnyx")
    await _client(requests, reject_premium=True).speak_unavailable("v3:call-2", command_id="cmd-2", locale="fr")
    assert [(r["service_level"], r["language"]) for r in requests] == [("premium", "fr-CA"), ("basic", "en-US")]
    assert requests[0]["command_id"] != requests[1]["command_id"]
    assert "status': 422" in caplog.text and "90062" in caplog.text
    assert "/calls/{call_control_id}/actions/speak" in caplog.text
    assert "v3:call-2" not in caplog.text
    assert API_KEY not in caplog.text
    assert "indisponible" not in caplog.text


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
