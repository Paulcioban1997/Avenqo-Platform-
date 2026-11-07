from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.models import VoiceCall
from tests.backend.test_voice_agent import _seed_retell_call, _voice_database


def test_resolve_call_requires_existing_retell_id_and_never_mints(tmp_path) -> None:
    engine, session, _company, config, _, service = _voice_database(tmp_path)
    try:
        with pytest.raises(LookupError, match="Correlated tenant call not found"):
            service._resolve_call(config, "retell-missing")
        assert session.scalar(select(func.count()).select_from(VoiceCall)) == 0

        created = _seed_retell_call(session, config, "retell-existing")
        session.commit()
        resolved = service._resolve_call(config, "retell-existing")
        assert resolved.id == created.id
        assert session.scalar(select(func.count()).select_from(VoiceCall)) == 1
    finally:
        session.close()
        engine.dispose()


def test_resolve_call_does_not_auto_pick_the_only_unmatched_in_progress_call(tmp_path) -> None:
    engine, session, _company, config, _, service = _voice_database(tmp_path)
    try:
        unmatched = VoiceCall(
            company_id=config.company_id,
            config_id=config.id,
            retell_call_id=None,
            caller_phone="+15145550123",
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        session.add(unmatched)
        session.commit()

        with pytest.raises(LookupError, match="Correlated tenant call not found"):
            service._resolve_call(config, "retell-late-tool")
        session.refresh(unmatched)
        assert unmatched.retell_call_id is None
        assert session.scalar(select(func.count()).select_from(VoiceCall)) == 1
    finally:
        session.close()
        engine.dispose()


def test_resolve_call_concurrent_unmatched_calls_require_explicit_header(tmp_path) -> None:
    engine, session, _company, config, _, service = _voice_database(tmp_path)
    try:
        first = VoiceCall(
            company_id=config.company_id,
            config_id=config.id,
            retell_call_id=None,
            caller_phone="+15145550111",
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        second = VoiceCall(
            company_id=config.company_id,
            config_id=config.id,
            retell_call_id=None,
            caller_phone="+15145550112",
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        session.add_all([first, second])
        session.commit()

        with pytest.raises(LookupError, match="Correlated tenant call not found"):
            service._resolve_call(config, "retell-concurrent-a")

        bound = service._resolve_call(
            config,
            "retell-concurrent-a",
            avenqo_call_id=str(first.id),
        )
        assert bound.id == first.id
        assert bound.retell_call_id == "retell-concurrent-a"
        session.refresh(second)
        assert second.retell_call_id is None

        with pytest.raises(PermissionError, match="Call correlation conflict"):
            service._resolve_call(
                config,
                "retell-concurrent-b",
                avenqo_call_id=str(first.id),
            )
        with pytest.raises(LookupError, match="Correlated tenant call not found"):
            service._resolve_call(config, "retell-concurrent-a", avenqo_call_id=str(uuid4()))
        assert session.scalar(select(func.count()).select_from(VoiceCall)) == 2
    finally:
        session.close()
        engine.dispose()


def test_execute_tool_does_not_create_synthetic_voice_call(tmp_path) -> None:
    engine, session, _company, config, _, service = _voice_database(tmp_path)
    try:
        result = asyncio.run(
            service.execute_tool(
                config,
                "retell-synthetic",
                "action-synthetic",
                "get_business_info",
                {},
            )
        )
        assert result == {"success": False, "error": "Correlated tenant call not found"}
        assert session.scalar(select(func.count()).select_from(VoiceCall)) == 0
    finally:
        session.close()
        engine.dispose()
