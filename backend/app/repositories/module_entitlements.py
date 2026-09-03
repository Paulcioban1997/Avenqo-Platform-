"""Adaptateur SQLAlchemy pour les droits d'accÃ¨s aux modules."""

from sqlalchemy.orm import Session

from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


class SQLAlchemyModuleEntitlements:
    """Lit les droits d'accÃ¨s actifs dans la base de donnÃ©es Avenqo."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def is_active(self, tenant: TenantContext, module_code: str) -> bool:
        return ModuleEntitlementService(self._session).can_use_module(
            tenant, module_code
        )
