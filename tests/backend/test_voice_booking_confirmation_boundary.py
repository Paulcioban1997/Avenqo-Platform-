"""No paid providers: Voice booking intent must not bypass confirmation."""
from uuid import uuid4
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.ai.tools.business.crm_tools import CreateAppointmentArgs, CreateAppointmentTool
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.models.crm import CRMAppointment, CRMClient
from tests.backend.test_voice_module_permissions import _activate, _company, _engine


def _executor(db, company, owner, tenant):
    from backend.app.ai.tools.authorization import ToolAuthorizationPolicy
    from backend.app.ai.tools.business.registry_factory import build_business_tool_registry
    from backend.app.ai.tools.executor import ToolExecutor
    from backend.app.ai.tools.idempotency import AIToolExecutionIdempotencyStore
    from backend.app.assistants.registry import build_default_assistant_registry
    from backend.app.core.permissions import permissions_for
    from backend.app.models import UserRole
    from tests.backend.test_voice_module_permissions import BOOKING, _grant
    _grant(db, company, BOOKING, owner.id)
    db.commit()
    registry = build_business_tool_registry(db, SimpleNamespace(), SimpleNamespace())
    tool = registry.get("create_appointment")
    tool.run = AsyncMock(return_value=ToolResult(success=True, data={"fixture": True}))
    executor = ToolExecutor(registry, ToolAuthorizationPolicy(db, build_default_assistant_registry(registry)),
                            AIToolExecutionIdempotencyStore(db))
    context = ToolExecutionContext(tenant=tenant, user_id=owner.id, permissions=permissions_for(UserRole.OWNER),
        selected_agent_id="crm", conversation_id=uuid4(), request_id=str(uuid4()), voice_path=True)
    arguments = {"client_name_or_id": "Disposable Fixture", "title": "Configured fixture appointment",
                 "start_time": "2030-01-07T14:00:00-05:00", "confirmed": False}
    return executor, context, arguments, tool.run


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed_confirmation", [False, True])
@pytest.mark.parametrize("locale,message", [
    ("fr-CA", "Je voudrais un rendez-vous demain à 14h, mais ne réservez pas encore."),
    ("en-CA", "Do not book an appointment tomorrow at 14:00. I have not confirmed."),
    ("ro-RO", "Nu confirmați programarea de mâine la 14:00."),
    ("fr-CA", "Un rendez-vous demain à 14h serait-il possible ?"),
    ("en-CA", "Maybe book an appointment tomorrow at 14:00, I am not sure yet."),
    ("ro-RO", "Poate mâine la 14:00, încă nu sunt sigur."),
])
async def test_executor_cannot_promote_voice_intent_or_model_flag_to_consent(tmp_path, locale, message, claimed_confirmation):
    with Session(_engine(tmp_path, "executor-negative.db")) as db:
        company, owner = _company(db, "executor-negative")
        tenant = _activate(db, company, "voice", "crm")
        executor, context, arguments, run = _executor(db, company, owner, tenant)
        result = await executor.execute("create_appointment", replace(context, user_message=message, locale=locale),
                                        {**arguments, "confirmed": claimed_confirmation})
        assert result.data.get("confirmation_required") is True
        run.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_details", [False, True])
async def test_voice_yes_confirms_only_the_proposed_booking_details(tmp_path, changed_details):
    with Session(_engine(tmp_path, "executor-consent.db")) as db:
        company, owner = _company(db, "executor-consent")
        tenant = _activate(db, company, "voice", "crm")
        executor, context, arguments, run = _executor(db, company, owner, tenant)
        first = await executor.execute("create_appointment", replace(context, user_message="Please review these details."), arguments)
        assert first.data["confirmation_required"] is True
        proposed = {**arguments, "start_time": "2030-01-07T15:00:00-05:00"} if changed_details else arguments
        result = await executor.execute("create_appointment", replace(context, request_id=str(uuid4()), user_message="yes", locale="en-CA"), proposed)
        if changed_details:
            assert result.data.get("confirmation_required") is True
            run.assert_not_called()
            # After a new proposal, a generic yes must not approve an older slot.
            stale = await executor.execute("create_appointment", replace(context, request_id=str(uuid4()), user_message="yes", locale="en-CA"), arguments)
            assert stale.data.get("confirmation_required") is True
            run.assert_not_called()
        else:
            assert result.success
            run.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("locale,message", [
    ("fr-CA", "Je voudrais un rendez-vous demain à 14h, mais ne réservez pas encore."),
    ("en-CA", "Can I book an appointment tomorrow at 14:00? Please confirm the details first."),
    ("ro-RO", "Aș dori o programare mâine la 14:00. Nu confirmați încă."),
])
async def test_voice_intent_requires_confirmation_before_any_crm_write(tmp_path, locale, message):
    engine = _engine(tmp_path, "confirmation.db")
    with Session(engine) as db:
        company, owner = _company(db, "confirmation-fixture")
        tenant = _activate(db, company, "voice", "crm")
        db.commit()
        context = ToolExecutionContext(
            tenant=tenant, user_id=owner.id,
            permissions=frozenset({"ai:use", "crm:appointments:write"}),
            request_id=str(uuid4()), user_message=message, locale=locale, voice_path=True,
        )
        result = await CreateAppointmentTool(db).run(context, CreateAppointmentArgs(
            client_name_or_id="Disposable Fixture", title="Configured fixture appointment",
            start_time="2030-01-07T14:00:00-05:00", confirmed=False,
        ))
        assert not result.success
        assert result.data.get("confirmation_required") is True
        assert db.scalar(select(func.count()).select_from(CRMAppointment)) == 0
        assert db.scalar(select(func.count()).select_from(CRMClient)) == 0
    engine.dispose()
