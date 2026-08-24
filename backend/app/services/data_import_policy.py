"""Politique CORE d'import de données — indépendante des modules optionnels.

L'ingestion de données (Connections / "Charger mes données") est une
capacité de plateforme disponible dès l'offre Demo, sans activer aucun
module métier optionnel (retail/crm/accounting). Seules des limites
dépendant du plan (nombre de datasets, taille de fichier) s'appliquent ici.
L'activation d'un module optionnel reste requise uniquement pour EXÉCUTER
une capacité métier sur un dataset déjà importé (voir
`CapabilityExecutionGate`).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Company, Dataset
from payments.plans import data_import_limits_for
from shared.ai_engine.contracts import TenantContext


class DataImportQuotaExceeded(ValueError):
    """Le nombre de datasets déjà importés atteint la limite de l'offre."""


class DataImportPolicy:
    """Résout les limites CORE d'import de données pour le plan d'un tenant."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def max_upload_bytes(self, tenant: TenantContext, global_ceiling_bytes: int) -> int:
        """Le plan ne peut jamais dépasser le plafond technique global."""

        limits = data_import_limits_for(self._plan_code(tenant))
        return min(global_ceiling_bytes, limits.max_file_mb * 1024 * 1024)

    def check_dataset_quota(self, tenant: TenantContext) -> None:
        limits = data_import_limits_for(self._plan_code(tenant))
        count = self._session.scalar(
            select(func.count()).select_from(Dataset).where(Dataset.company_id == tenant.company_id)
        ) or 0
        if count >= limits.max_datasets:
            raise DataImportQuotaExceeded(
                f"Limite de {limits.max_datasets} jeux de données atteinte pour votre offre."
            )

    def _plan_code(self, tenant: TenantContext) -> str:
        plan = self._session.scalar(
            select(Company.subscription_plan).where(Company.id == tenant.company_id)
        )
        return plan or "demo"
