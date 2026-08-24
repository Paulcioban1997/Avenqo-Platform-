from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models import Base, Company, CompanyModule, CompanyModuleStatus, Module
from backend.app.repositories import SQLAlchemyModuleEntitlements
from shared.ai_engine.contracts import TenantContext


def test_sqlalchemy_entitlements_require_active_company_module() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Company.__table__, Module.__table__, CompanyModule.__table__],
    )

    with Session(engine) as session:
        company = Company(
            name="Example Company",
            slug="example-company",
            email="admin@example.com",
            country="FR",
            timezone="Europe/Paris",
            industry="retail",
            subscription_plan="demo",
        )
        module = Module(name="RetailSenseAI", code="retail")
        session.add_all([company, module])
        session.flush()

        entitlement = CompanyModule(
            company_id=company.id,
            module_id=module.id,
            activated_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            status=CompanyModuleStatus.ACTIVE,
        )
        session.add(entitlement)
        session.commit()

        reader = SQLAlchemyModuleEntitlements(session)
        tenant = TenantContext(company.id)

        assert reader.is_active(tenant, "retail") is True

        entitlement.status = CompanyModuleStatus.PAUSED
        session.commit()

        assert reader.is_active(tenant, "retail") is False