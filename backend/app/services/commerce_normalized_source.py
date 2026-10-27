"""Retail snapshots from normalized commerce records when CSV artifacts are missing.

This restores WooCommerce/Shopify as selectable Retail sources without inventing
rows and without falling back to an uploaded Superstore CSV.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import CommerceConnection, NormalizedCommerceRecord
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.cleaning import CleaningReport
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset
from shared.ai_engine.dataset_ingestion.profiling import CompanyDatasetProfile
from shared.ai_engine.dataset_ingestion.quality import assess_quality
from shared.ai_engine.dataset_ingestion.readiness import assess_capability_readiness

logger = logging.getLogger("avenqo.commerce.normalized_source")

_NUMERIC_FIELDS = frozenset(
    {
        "unit_price",
        "inventory_level",
        "quantity",
        "total_amount",
        "discount_amount",
        "refund_amount",
    }
)


class _UnusedCollaborator:
    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)


def connection_has_normalized_records(
    session: Session, connection: CommerceConnection
) -> bool:
    count = session.scalar(
        select(func.count())
        .select_from(NormalizedCommerceRecord)
        .where(
            NormalizedCommerceRecord.company_id == connection.company_id,
            NormalizedCommerceRecord.connection_id == connection.id,
            NormalizedCommerceRecord.deleted.is_(False),
        )
    )
    return int(count or 0) > 0


def build_connector_snapshot_rows(
    session: Session,
    tenant: TenantContext,
    connection: CommerceConnection,
) -> list[dict[str, Any]]:
    from backend.app.services.commerce_sync_service import CommerceSyncService

    content = CommerceSyncService(
        session,
        _UnusedCollaborator(),
        _UnusedCollaborator(),
        _UnusedCollaborator(),
    ).build_retail_snapshot(tenant, connection)
    if not content:
        return []
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(io.StringIO(content.decode("utf-8"))):
        row = dict(raw)
        for field in _NUMERIC_FIELDS:
            value = row.get(field)
            if value in (None, ""):
                continue
            try:
                row[field] = float(value)
            except (TypeError, ValueError):
                pass
        rows.append(row)
    return rows


def prepared_from_normalized_connection(
    session: Session,
    tenant: TenantContext,
    connection: CommerceConnection,
    dataset_id: UUID | None,
) -> PreparedCompanyDataset | None:
    rows = build_connector_snapshot_rows(session, tenant, connection)
    if not rows:
        return None
    columns = tuple(dict.fromkeys(key for row in rows for key in row))
    canonical = {column: column for column in columns}
    report = CleaningReport(
        rows_before=len(rows),
        rows_after=len(rows),
        duplicates_removed=0,
        numeric_conversions=0,
        date_conversions=0,
        null_cells_detected=0,
        invalid_rows=0,
        column_count=len(columns),
    )
    return PreparedCompanyDataset(
        company_id=tenant.company_id,
        dataset_id=dataset_id or connection.id,
        version=1,
        canonical_columns=canonical,
        rows=tuple(rows),
        profile=CompanyDatasetProfile(
            row_count=len(rows),
            column_count=len(columns),
        ),
        mapping=(),
        cleaning_report=report,
        quality=assess_quality(report),
        capability_readiness=assess_capability_readiness(set(canonical.values())),
    )


def try_restore_connector_retail_dataset(
    session: Session,
    ingestion: Any,
    tenant: TenantContext,
    connection: CommerceConnection,
):
    upload = getattr(ingestion, "upload", None)
    if not callable(upload):
        return None
    try:
        from backend.app.services.commerce_sync_service import CommerceSyncService

        return CommerceSyncService(
            session,
            _UnusedCollaborator(),
            _UnusedCollaborator(),
            ingestion,
        ).ensure_retail_snapshot(tenant, connection)
    except Exception:
        logger.exception(
            "Unable to rematerialize connector retail dataset connection=%s company=%s",
            connection.id,
            tenant.company_id,
        )
        return None
