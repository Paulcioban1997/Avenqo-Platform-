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
    left_uniqueness: float
    right_uniqueness: float


@dataclass(frozen=True, slots=True)
class MappingRelationshipEvidence:
    canonical_field: str
    source_column: str
    peer_dataset_id: UUID
    peer_column: str
    overlap_ratio: float
    confidence: float


_UNIQUE_THRESHOLD = 0.95


def _cardinality(left_uniqueness: float, right_uniqueness: float) -> str:
    """Classify 1:1 / 1:N / N:1 directly from tenant-local uniqueness ratios.

    Never inferred from column names. `many_to_many` is reserved for the
    (rarer) case where neither side is confidently unique, which is only
    reachable here because callers already required at least one side to
    clear a lower bar before evidence is even collected.
    """

    left_unique = left_uniqueness >= _UNIQUE_THRESHOLD
    right_unique = right_uniqueness >= _UNIQUE_THRESHOLD
    if left_unique and right_unique:
        return "one_to_one"
    if left_unique and not right_unique:
        return "one_to_many"
    if right_unique and not left_unique:
        return "many_to_one"
    return "many_to_many"


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
                left_uniqueness=round(left_unique, 4),
                right_uniqueness=round(right_unique, 4),
            )
        )
    return tuple(evidence)


class DatasetRelationshipService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve_mapping_conflicts(
        self,
        tenant: TenantContext,
        dataset: Dataset,
        conflicts: Sequence[Mapping[str, Any]],
        ingestion,
    ) -> tuple[MappingRelationshipEvidence, ...]:
        """Resolve identifier conflicts only when tenant data gives one clear winner."""

        candidate_rows = ingestion._reload_current_version_rows(dataset)
        peers = self._session.scalars(
            select(Dataset).where(
                Dataset.company_id == tenant.company_id,
                Dataset.id != dataset.id,
                Dataset.status == DatasetStatus.READY,
            )
        ).all()
        resolved: list[MappingRelationshipEvidence] = []
        for conflict in conflicts:
            canonical = str(conflict.get("canonical_field") or "")
            columns = tuple(str(column) for column in conflict.get("columns") or ())
            if (canonical != "id" and not canonical.endswith("_id")) or len(columns) < 2:
                continue

            evidence: list[MappingRelationshipEvidence] = []
            for peer in peers:
                try:
                    prepared = ingestion.get_prepared_dataset(tenant, peer.id)
                except Exception:
                    continue
                peer_columns = [
                    source
                    for source, field in prepared.canonical_columns.items()
                    if field == canonical
                ]
                for source_column in columns:
                    source_values = _values(candidate_rows, source_column)
                    if not source_values:
                        continue
                    for peer_column in peer_columns:
                        peer_values = _values(prepared.rows, peer_column)
                        if not peer_values:
                            continue
                        overlap = len(source_values & peer_values) / min(
                            len(source_values), len(peer_values)
                        )
                        if overlap < 0.5:
                            continue
                        uniqueness = max(
                            len(source_values) / max(_present_count(candidate_rows, source_column), 1),
                            len(peer_values) / max(_present_count(prepared.rows, peer_column), 1),
                        )
                        if uniqueness < 0.8:
                            continue
                        evidence.append(
                            MappingRelationshipEvidence(
                                canonical_field=canonical,
                                source_column=source_column,
                                peer_dataset_id=peer.id,
                                peer_column=peer_column,
                                overlap_ratio=round(overlap, 4),
                                confidence=round(min(1.0, 0.6 * overlap + 0.4 * uniqueness), 4),
                            )
                        )

            best_by_column: dict[str, MappingRelationshipEvidence] = {}
            for item in evidence:
                current = best_by_column.get(item.source_column)
                if current is None or item.confidence > current.confidence:
                    best_by_column[item.source_column] = item
            ranked = sorted(best_by_column.values(), key=lambda item: item.confidence, reverse=True)
            if ranked and (len(ranked) == 1 or ranked[0].confidence > ranked[1].confidence):
                resolved.append(ranked[0])
        return tuple(resolved)

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
                cardinality = _cardinality(item.left_uniqueness, item.right_uniqueness)
                if cardinality == "many_to_many" and not self._has_junction_evidence(
                    tenant, left.id, right.id
                ):
                    # Neither side is confidently unique and no tenant-local
                    # junction dataset backs an N:N interpretation: report as
                    # unclassified rather than fabricate a cardinality claim.
                    cardinality = "unclassified"
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
                        cardinality=cardinality,
                    )
                )
        self._session.commit()

    def _has_junction_evidence(
        self, tenant: TenantContext, left_dataset_id: UUID, right_dataset_id: UUID
    ) -> bool:
        """True when a third tenant dataset already links both ends.

        A junction (association) dataset is one that has its own recorded
        relationship to `left_dataset_id` AND a separate recorded
        relationship to `right_dataset_id` (typically via two different
        canonical `_id` fields, e.g. an order-lines table linking orders and
        products). This is tenant-local, evidence-based support for N:N,
        never inferred from column names alone.
        """

        linked_to_left = {
            row[0]
            for row in self._session.execute(
                select(DatasetRelationship.left_dataset_id).where(
                    DatasetRelationship.company_id == tenant.company_id,
                    DatasetRelationship.right_dataset_id == left_dataset_id,
                )
            ).all()
        } | {
            row[0]
            for row in self._session.execute(
                select(DatasetRelationship.right_dataset_id).where(
                    DatasetRelationship.company_id == tenant.company_id,
                    DatasetRelationship.left_dataset_id == left_dataset_id,
                )
            ).all()
        }
        linked_to_right = {
            row[0]
            for row in self._session.execute(
                select(DatasetRelationship.left_dataset_id).where(
                    DatasetRelationship.company_id == tenant.company_id,
                    DatasetRelationship.right_dataset_id == right_dataset_id,
                )
            ).all()
        } | {
            row[0]
            for row in self._session.execute(
                select(DatasetRelationship.right_dataset_id).where(
                    DatasetRelationship.company_id == tenant.company_id,
                    DatasetRelationship.left_dataset_id == right_dataset_id,
                )
            ).all()
        }
        junction_candidates = (linked_to_left & linked_to_right) - {left_dataset_id, right_dataset_id}
        return bool(junction_candidates)


def _values(rows: Sequence[Mapping[str, Any]], column: str) -> set[str]:
    return {
        str(row[column]).strip().casefold()
        for row in rows
        if row.get(column) is not None and str(row[column]).strip()
    }


def _present_count(rows: Sequence[Mapping[str, Any]], column: str) -> int:
    return sum(row.get(column) is not None and bool(str(row[column]).strip()) for row in rows)