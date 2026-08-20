"""Résolution du dataset le plus récent et prêt d'un tenant (Phase 30).

Réutilise le pipeline Phase 26/27 tel quel : aucune nouvelle lecture de
fichier brut, aucune duplication de logique de préparation.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.tools.exceptions import ToolUnavailableError
from backend.app.models import Dataset, DatasetStatus
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset


def latest_ready_dataset(session: Session, tenant: TenantContext) -> Dataset | None:
    return session.scalar(
        select(Dataset)
        .where(Dataset.company_id == tenant.company_id, Dataset.status == DatasetStatus.READY)
        .order_by(Dataset.uploaded_at.desc())
    )


def load_latest_prepared_dataset(
    session: Session,
    ingestion: CompanyDatasetIngestionService,
    tenant: TenantContext,
) -> PreparedCompanyDataset:
    """Charge le dernier dataset prêt du tenant, ou lève `ToolUnavailableError`."""

    dataset = latest_ready_dataset(session, tenant)
    if dataset is None:
        raise ToolUnavailableError(
            "No business data is available yet for this company. Connect your business data first."
        )
    return ingestion.get_prepared_dataset(tenant, dataset.id)
