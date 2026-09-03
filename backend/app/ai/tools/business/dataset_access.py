"""Résolution du dataset le plus récent et prêt d'un tenant (Phase 30).

Réutilise le pipeline Phase 26/27 tel quel : aucune nouvelle lecture de
fichier brut, aucune duplication de logique de préparation.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.tools.exceptions import ToolUnavailableError
from backend.app.models import Dataset, DatasetStatus
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset

logger = logging.getLogger("avenqo.ai.dataset_access")


def latest_ready_dataset(session: Session, tenant: TenantContext) -> Dataset | None:
    dataset = session.scalar(
        select(Dataset)
        .where(Dataset.company_id == tenant.company_id, Dataset.status == DatasetStatus.READY)
        .order_by(Dataset.uploaded_at.desc())
    )
    logger.info(
        "ai_dataset_resolution tenant_id=%s dataset_id=%s dataset_status=%s ready_found=%s",
        tenant.company_id,
        dataset.id if dataset is not None else None,
        dataset.status.value if dataset is not None else None,
        str(dataset is not None).lower(),
    )
    return dataset


def load_latest_prepared_dataset(
    session: Session,
    ingestion: CompanyDatasetIngestionService,
    tenant: TenantContext,
    required_fields: frozenset[str] = frozenset(),
) -> PreparedCompanyDataset:
    """Charge la même vue READY composée que les pages Retail du tenant."""

    snapshot = TenantAnalyticsService(session, ingestion).load(tenant)
    source = snapshot.source_for(required_fields)
    if source is None and (dataset := latest_ready_dataset(session, tenant)) is not None:
        fallback = ingestion.get_prepared_dataset(tenant, dataset.id)
        if required_fields <= set(fallback.canonical_columns.values()):
            source = fallback
    if source is None:
        logger.warning(
            "ai_prepared_dataset tenant_id=%s dataset_id=%s dataset_status=%s prepared_dataset_available=false",
            tenant.company_id,
            None,
            None,
        )
        if snapshot.datasets:
            available = {
                canonical
                for prepared in snapshot.prepared
                for canonical in prepared.canonical_columns.values()
            }
            missing = sorted(required_fields - available)
            details = ", ".join(missing) if missing else "dataset relationships"
            raise ToolUnavailableError(
                "Business data is connected but not yet computable. "
                f"Complete mapping or relationships for: {details}."
            )
        raise ToolUnavailableError(
            "No business data is available yet for this company. Connect your business data first."
        )
    logger.info(
        "ai_prepared_dataset tenant_id=%s dataset_id=%s dataset_status=%s prepared_dataset_available=true",
        tenant.company_id,
        source.dataset_id,
        DatasetStatus.READY.value,
    )
    return source
