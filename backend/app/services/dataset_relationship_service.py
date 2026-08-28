from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from backend.app.models import Dataset, DatasetRelationship, DatasetStatus
from shared.ai_engine.contracts import TenantContext


@dataclass(frozen=True, slots=True)
class RelationshipEvidence:
    canonical_field: str
    left_column: str
    right_column: str
    overlap_ratio: float
    confidence: float


def discover_relationships(
    left_rows: Sequence[Mapping[str, Any]],
    left_mapping: Mapping[str, str],
    right_rows: Sequence[Mapping[str, Any]],
    right_mapping: Mapping[str, str],
) -> tuple[RelationshipEvidence, ...]:
    """Return conservative identifier relationships without merging datasets."""

    left_by_canonical = {canonical: source for source, canonical in left_mapping.items()}
    right_by_canonical = {canonical: source for source, canonical in right_mapping.items()}
    evidence: list[RelationshipEvidence] = []
    for canonical in sorted(left_by_canonical.keys() & right_by_canonical.keys()):
        if canonical != "id" and not canonical.endswith("_id"):
            continue
        left_column = left_by_canonical[canonical]
        right_column = right_by_canonical[canonical]
        left_values = _values(left_rows, left_column)
        right_values = _values(right_rows, right_column)
        if not left_values or not right_values:
            continue
        left_unique = len(left_values) / max(_present_count(left_rows, left_column), 1)
        right_unique = len(right_values) / max(_present_count(right_rows, right_column), 1)
        if max(left_unique, right_unique) < 0.8:
            continue
        overlap = len(left_values & right_values) / min(len(left_values), len(right_values))
        if overlap < 0.5:
            continue
        evidence.append(
            RelationshipEvidence(
                canonical_field=canonical,
                left_column=left_column,
                right_column=right_column,
                overlap_ratio=round(overlap, 4),
                confidence=round(min(1.0, 0.6 * overlap + 0.4 * max(left_unique, right_unique)), 4),
            )
        )
    return tuple(evidence)


class DatasetRelationshipService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def refresh_for_dataset(self, tenant: TenantContext, dataset: Dataset, ingestion) -> None:
        self._session.execute(
            delete(DatasetRelationship).where(
                DatasetRelationship.company_id == tenant.company_id,
                or_(
                    DatasetRelationship.left_dataset_id == dataset.id,
                    DatasetRelationship.right_dataset_id == dataset.id,
                ),
            )
        )
        current = ingestion.get_prepared_dataset(tenant, dataset.id)
        peers = self._session.scalars(
            select(Dataset).where(
                Dataset.company_id == tenant.company_id,
                Dataset.id != dataset.id,
                Dataset.status == DatasetStatus.READY,
            )
        ).all()
        for peer in peers:
            try:
                other = ingestion.get_prepared_dataset(tenant, peer.id)
            except Exception:
                continue
            left, right = sorted((dataset, peer), key=lambda item: str(item.id))
            left_prepared, right_prepared = (current, other) if left.id == dataset.id else (other, current)
            for item in discover_relationships(
                left_prepared.rows,
                left_prepared.canonical_columns,
                right_prepared.rows,
                right_prepared.canonical_columns,
            ):
                self._session.add(
                    DatasetRelationship(
                        company_id=tenant.company_id,
                        left_dataset_id=left.id,
                        right_dataset_id=right.id,
                        left_column=item.left_column,
                        right_column=item.right_column,
                        canonical_field=item.canonical_field,
                        overlap_ratio=item.overlap_ratio,
                        confidence=item.confidence,
                    )
                )
        self._session.commit()


def _values(rows: Sequence[Mapping[str, Any]], column: str) -> set[str]:
    return {
        str(row[column]).strip().casefold()
        for row in rows
        if row.get(column) is not None and str(row[column]).strip()
    }


def _present_count(rows: Sequence[Mapping[str, Any]], column: str) -> int:
    return sum(row.get(column) is not None and bool(str(row[column]).strip()) for row in rows)