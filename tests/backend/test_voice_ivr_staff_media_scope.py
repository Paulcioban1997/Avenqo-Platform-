"""Regression for Telnyx IVR employee private ticket with public media enabled.

Production incident 2026-11-12: after successful PIN, staff media streams
received WebSocket 4403 "Media authorization scope mismatch" because the
WebSocket unconditionally chose public_mode=True.
"""
from datetime import datetime, timezone

import pytest

from backend.app.voice.telnyx_media import (
    claim_media_start,
    issue_media_client_state,
    release_media_session,
    resolve_media_socket_context,
)
from tests.backend.test_telnyx_media import authorized_media_call


def _start(env, ticket):
    return {
        "client_state": ticket,
        "call_control_id": env.call.telnyx_call_control_id,
        "to": env.config.telnyx_phone_number,
    }


def test_staff_ivr_private_ticket_accepted_with_inbound_media_enabled(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.call.source_context = {
        **(env.call.source_context or {}),
        "ivr_stage": "staff_authenticated",
        "pin_gather_status": "authenticated",
    }
    env.db.commit()

    public_mode, call, config, company = resolve_media_socket_context(
        env.db, env.settings, env.call.id
    )
    assert public_mode is False
    assert call.id == env.call.id
    assert config.id == env.config.id
    assert company.id == env.company.id

    private_ticket = issue_media_client_state(
        env.db, env.settings, env.call.id, public_mode=False
    )
    claim = claim_media_start(
        env.db, env.settings, env.call.id,
        _start(env, private_ticket), public_mode=public_mode,
    )
    release_media_session(env.db, env.call.id, claim)


def test_public_ivr_still_uses_public_media_ticket(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.call.caller_type = "CLIENT"
    env.call.authenticated_user_id = None
    env.call.source_context = {"ivr_stage": "customer_public"}
    env.auth.revoked_at = datetime.now(timezone.utc)
    env.db.commit()

    public_mode, _call, _config, _company = resolve_media_socket_context(
        env.db, env.settings, env.call.id
    )
    assert public_mode is True
    public_ticket = issue_media_client_state(
        env.db, env.settings, env.call.id, public_mode=True
    )
    claim = claim_media_start(
        env.db, env.settings, env.call.id,
        _start(env, public_ticket), public_mode=public_mode,
    )
    release_media_session(env.db, env.call.id, claim)


def test_forged_staff_ivr_stage_without_valid_session_fails_closed(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.call.source_context = {"ivr_stage": "staff_authenticated"}
    env.auth.revoked_at = datetime.now(timezone.utc)
    env.db.commit()

    with pytest.raises(PermissionError, match="Verified staff call required"):
        resolve_media_socket_context(env.db, env.settings, env.call.id)


def test_explicit_private_only_media_remains_private(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = False
    public_mode, _call, _config, _company = resolve_media_socket_context(
        env.db, env.settings, env.call.id
    )
    assert public_mode is False
