import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.crm import CRMService as CRMServiceModel
from backend.app.ai.tools.business.crm_tools import GetCrmServicesTool, GetCrmServicesArgs
from backend.app.ai.tools.contracts import ToolExecutionContext
from shared.ai_engine.contracts import TenantContext

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()

@pytest.mark.asyncio
async def test_get_crm_services_tool(db_session: Session):
    company_id = uuid4()
    company = Company(
        id=company_id,
        name="Physio Clinique",
        slug="physio-clinique",
        email="contact@physioclinique.ca",
        country="Canada",
        timezone="America/Toronto",
        industry="Health",
        subscription_plan="professional",
        preferred_language="fr",
    )
    db_session.add(company)

    s1 = CRMServiceModel(
        id=uuid4(),
        company_id=company_id,
        name="Consultation initiale de physiothérapie",
        description="Bilan complet 60 minutes avec physiothérapeute agréé.",
        duration_minutes=60,
        price=120.0,
        currency="CAD",
        category="Physiothérapie",
        is_active=True,
        is_published=True,
        is_approved_by_owner=True,
    )
    s2 = CRMServiceModel(
        id=uuid4(),
        company_id=company_id,
        name="Massage thérapeutique",
        description="Séance de 45 minutes.",
        duration_minutes=45,
        price=85.0,
        currency="CAD",
        category="Massothérapie",
        is_active=True,
        is_published=True,
        is_approved_by_owner=True,
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    tool = GetCrmServicesTool(db_session)
    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company_id, user_id=uuid4()),
        user_id=uuid4(),
        request_id="test-req-crm-1",
        permissions=frozenset({"ai:use", "crm:appointments:read"}),
        voice_path=False,
    )

    # 1. Fetch all
    res = await tool.run(context, GetCrmServicesArgs())
    assert res.success is True
    assert res.data["count"] == 2
    assert any(s["name"] == "Consultation initiale de physiothérapie" for s in res.data["services"])

    # 2. Search "physio"
    res_search = await tool.run(context, GetCrmServicesArgs(search="physio"))
    assert res_search.success is True
    assert res_search.data["count"] == 1
    assert res_search.data["services"][0]["name"] == "Consultation initiale de physiothérapie"
    assert res_search.data["services"][0]["duration_minutes"] == 60
    assert res_search.data["services"][0]["price"] == 120.0
