"""Adaptateur SQLAlchemy pour les droits d'accÃ¨s aux modules."""

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models import CompanyModule, CompanyModuleStatus, Module
from shared.ai_engine.contracts import TenantContext


class SQLAlchemyModuleEntitlements:
    """Lit les droits d'accÃ¨s actifs dans la base de donnÃ©es Avenqo."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def is_active(self, tenant: TenantContext, module_code: str) -> bool:
        now = datetime.now(timezone.utc)
        statement = (
            select(CompanyModule.id)
            .join(Module, CompanyModule.module_id == Module.id)
            .where(
                CompanyModule.company_id == tenant.company_id,
                CompanyModule.status == CompanyModuleStatus.ACTIVE,
                CompanyModule.activated_at <= now,
                or_(CompanyModule.expires_at.is_(None), CompanyModule.expires_at > now),
                Module.code == module_code,
                Module.is_active.is_(True),
            )
            .limit(1)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None  # Ce return veut dire : "Renvoie True si le module est actif pour l'entreprise, sinon False."
