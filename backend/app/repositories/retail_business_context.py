"""Lecture tenant-isolée de l'état métier RetailSense."""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from backend.app.models import Dataset, DatasetStatus, ModelRegistry
from modules.retailsense.assistant import BusinessReadiness
from shared.ai_engine.contracts import TenantContext


class SQLAlchemyRetailBusinessContext:
    def __init__(self, session: Session) -> None:
        self._session = session

    def readiness(self, tenant: TenantContext) -> BusinessReadiness:
        has_source = self._session.scalar(
            select(exists().where(
                Dataset.company_id == tenant.company_id,
                Dataset.status == DatasetStatus.VALIDATED,
            ))
        )
        if not has_source:
            return BusinessReadiness.NEEDS_CONNECTION

        has_active_results = self._session.scalar(
            select(exists().where(
                ModelRegistry.company_id == tenant.company_id,
                ModelRegistry.is_active.is_(True),
            ))
        )
        return BusinessReadiness.READY if has_active_results else BusinessReadiness.PREPARING