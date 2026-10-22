"""No paid providers: Voice booking intent must not bypass confirmation."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.ai.tools.business.crm_tools import CreateAppointmentArgs, CreateAppointmentTool
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.models.crm import CRMAppointment, CRMClient
from tests.backend.test_voice_module_permissions import _activate, _company, _engine


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
