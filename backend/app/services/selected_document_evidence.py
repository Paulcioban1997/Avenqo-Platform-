"""Read current selected documents without posting accounting entries or widening scope."""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from backend.app.models import Dataset
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger(__name__)


def inspect_selected_documents(db: Session, tenant: TenantContext) -> dict:
    from backend.app.voice.selected_source_intelligence import resolve_authorized_selected_sources
    from backend.app.dependencies.datasets import get_company_dataset_ingestion_service, get_data_import_policy

    resolution = resolve_authorized_selected_sources(db, tenant, require_data_read=True)
    result = {"state": resolution.state, "documents": []}
    if resolution.state != "READY":
        return result
    service = get_company_dataset_ingestion_service(
        db=db, quota=get_data_import_policy(db), dispatcher=None,
    )
    for source in resolution.sources:
        if not source.get("dataset_id"):
            continue
        item = {"dataset_id": source["dataset_id"], "name": source["name"]}
        try:
            # A long-lived Voice session must not retain an older version after re-import.
            dataset = db.scalar(select(Dataset).where(
                Dataset.id == UUID(source["dataset_id"]), Dataset.company_id == tenant.company_id,
            ).options(selectinload(Dataset.versions)).execution_options(populate_existing=True))
            if dataset is None:
                raise LookupError("Selected dataset unavailable")
            bundle, report = service.inspect_workbook_or_document(tenant, UUID(source["dataset_id"]))
            item.update(
                status="read", extraction=report.to_dict(),
                content=bundle.full_text[:6000],
                content_truncated=len(bundle.full_text) > 6000 or bundle.is_incomplete_source,
                content_sha256=bundle.sha256,
                sheets=[sheet.to_summary_dict() for sheet in bundle.sheets],
            )
        except Exception as exc:
            # No sensitive contents/paths in public errors or logs. Never fabricate zero totals.
            logger.warning("selected_document_read_failed dataset_id=%s error_type=%s", source["dataset_id"], type(exc).__name__)
            item.update(status="unavailable", extraction=None)
        result["documents"].append(item)
    return result
