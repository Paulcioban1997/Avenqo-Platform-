import base64
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from sqlalchemy import select

from backend.app.config.settings import Settings
from backend.app.models import VoiceCall
from backend.app.voice.providers import TelnyxClient, _ensure_base64_client_state
from tests.backend.test_voice_agent import signed_telnyx_webhook


def test_ensure_base64_client_state():
    # Plain text string must be base64-encoded
    raw = "dispatcher_nip_gather"
    encoded = _ensure_base64_client_state(raw)
    assert encoded is not None
    assert base64.b64decode(encoded.encode("ascii")).decode("utf-8") == raw

    # Already valid base64 must remain untouched
    existing_b64 = base64.b64encode(b'{"key": "value"}').decode("ascii")
    assert _ensure_base64_client_state(existing_b64) == existing_b64

    # None or empty returns None
    assert _ensure_base64_client_state(None) is None
    assert _ensure_base64_client_state("") is None


@pytest.mark.asyncio
async def test_telnyx_client_gather_using_speak_encodes_client_state():
    settings = Settings(
        TELNYX_API_KEY="test_key",
        TELNYX_PUBLIC_KEY="test_public_key",
    )
    client = TelnyxClient(settings)
    mock_request = AsyncMock(return_value={})
    client._request = mock_request

    await client.gather_using_speak(
        "cc-12345",
        text_prompt="Bienvenue chez Produits_Ero.",
        client_state="raw_unencoded_state",
        language="fr-CA",
    )

    mock_request.assert_awaited_once()
    args, kwargs = mock_request.call_args
    payload = kwargs["json"]
    assert payload["client_state"] is not None
    decoded = base64.b64decode(payload["client_state"].encode("ascii")).decode("utf-8")
    assert decoded == "raw_unencoded_state"


@pytest.mark.asyncio
async def test_telnyx_client_media_stream_payload_encodes_client_state():
    settings = Settings(
        TELNYX_API_KEY="test_key",
        TELNYX_MEDIA_ENABLED=True,
    )
    client = TelnyxClient(settings)
    payload = client.media_stream_payload(
        stream_url="wss://api.avenqo.ca/api/v1/voice/telnyx/media/call-id",
        client_state="plain_state_123",
        command_id="cmd-123",
    )
    assert payload["client_state"] is not None
    decoded = base64.b64decode(payload["client_state"].encode("ascii")).decode("utf-8")
    assert decoded == "plain_state_123"


def test_inbound_ivr_answers_then_prompts_menu_and_touche_2_routes_client(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    env.settings.telnyx_media_enabled = True
    env.settings.telnyx_media_inbound_enabled = True
    env.settings.telnyx_media_stream_base_url = "wss://api.avenqo.ca/api/v1/voice/telnyx/media"
    env.settings.openai_api_key = "fake-audio-key"
    env.settings.voice_realtime_supported_locales = ["fr"]
    env.binding.provider_connection_id = env.settings.telnyx_voice_connection_id

    # Configure IVR on tenant
    env.config.call_policy = {
        "ivr_enabled": True,
        "ivr_greeting": "Bienvenue chez Produits_Ero. Pour les employés, composez le 1. Pour le service clientèle, composez le 2."
    }
    env.session.commit()

    # 1. call.initiated -> Answers call
    init_res = env.send(env.event())
    assert init_res.status_code == 200
    assert init_res.json()["status"] == "answering"
    assert env.service.telnyx.commands[0][0] == "answer"
    assert env.service.telnyx.commands[0][1] == "inbound-control"

    # 2. call.answered -> Prompts IVR greeting with gather_using_speak
    ans_res = env.send(env.event("call.answered"))
    assert ans_res.status_code == 200
    assert ans_res.json()["ivr"] == "menu"

    # Verify gather_using_speak command recorded
    gather_cmds = [x for x in env.service.telnyx.commands if x[0] == "gather_using_speak"]
    assert len(gather_cmds) == 1
    # Extract client_state that Telnyx echoes back
    issued_client_state = gather_cmds[0][4]
    call = env.session.scalar(select(VoiceCall))
    assert (call.source_context or {}).get("ivr_stage") == "menu"

    # 3. call.gather.ended with digits="2" -> starts media stream in client mode
    gather_event = env.event("call.gather.ended")
    gather_event["data"]["payload"]["digits"] = "2"
    gather_event["data"]["payload"]["client_state"] = issued_client_state
    cust_res = env.send(gather_event)
    assert cust_res.status_code == 200
    assert cust_res.json()["caller_mode"] == "CLIENT"

    stream_cmds = [x for x in env.service.telnyx.commands if x[0] == "start_media_stream"]
    assert len(stream_cmds) == 1
    env.session.refresh(call)
    assert call.caller_type == "CLIENT"
    assert (call.source_context or {}).get("ivr_stage") == "customer_public"


def test_inbound_ivr_touche_1_prompts_employee_pin(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    env.settings.telnyx_media_enabled = True
    env.settings.telnyx_media_inbound_enabled = True
    env.settings.telnyx_media_stream_base_url = "wss://api.avenqo.ca/api/v1/voice/telnyx/media"
    env.settings.openai_api_key = "fake-audio-key"
    env.settings.voice_realtime_supported_locales = ["fr"]
    env.binding.provider_connection_id = env.settings.telnyx_voice_connection_id

    env.config.call_policy = {
        "ivr_enabled": True,
        "ivr_greeting": "Bienvenue chez Produits_Ero. Pour les employés, composez le 1. Pour le service clientèle, composez le 2."
    }
    env.session.commit()

    env.send(env.event())
    env.send(env.event("call.answered"))

    gather_cmds = [x for x in env.service.telnyx.commands if x[0] == "gather_using_speak"]
    assert len(gather_cmds) == 1
    issued_client_state = gather_cmds[0][4]

    # Touche 1 -> prompt PIN
    gather_event = env.event("call.gather.ended")
    gather_event["data"]["payload"]["digits"] = "1"
    gather_event["data"]["payload"]["client_state"] = issued_client_state
    staff_res = env.send(gather_event)
    assert staff_res.status_code == 200
    assert staff_res.json()["ivr_stage"] == "employee_pin_prompted"

    call = env.session.scalar(select(VoiceCall))
    assert (call.source_context or {}).get("ivr_stage") == "employee_pin"

    # Configure an employee PIN in DB
    from backend.app.voice.auth import VoiceCallerAuth
    from backend.app.models.user import User
    from backend.app.models.base import UserRole
    from backend.app.models.company_membership import CompanyMembership
    from shared.ai_engine.contracts import TenantContext
    employee = User(
        company_id=env.company.id,
        first_name="Jean",
        last_name="Employe",
        email="jean@produits-ero.ca",
        password_hash="mock-hash",
        phone="+15149998877",
        role=UserRole.USER,
        is_active=True,
    )
    env.session.add(employee)
    env.session.flush()
    env.session.add(CompanyMembership(company_id=env.company.id, user_id=employee.id, role=UserRole.USER, is_active=True))
    auth = VoiceCallerAuth(env.session, env.settings)
    auth.set_pin(TenantContext(company_id=env.company.id, user_id=employee.id), "USER", employee.id, "907182", phone_number="+15149998877")
    env.session.commit()

    # Enter PIN with trailing # from a different caller phone
    pin_gather_cmds = [x for x in env.service.telnyx.commands if x[0] == "gather_using_speak"]
    assert len(pin_gather_cmds) == 2
    pin_client_state = pin_gather_cmds[1][4]

    pin_event = env.event("call.gather.ended")
    pin_event["data"]["payload"]["digits"] = "907182#"
    pin_event["data"]["payload"]["client_state"] = pin_client_state
    pin_res = env.send(pin_event)
    assert pin_res.status_code == 200
    assert pin_res.json()["authenticated"] is True
    assert pin_res.json()["caller_mode"] == "STAFF"

    env.session.expire(call)
    call = env.session.get(VoiceCall, call.id)
    assert call.caller_type == "EMPLOYEE"
    assert (call.source_context or {}).get("ivr_stage") == "staff_authenticated"

