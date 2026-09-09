from __future__ import annotations

from uuid import uuid4

from backend.app.services.automatic_company_dataset_ingestion_service import (
    AutomaticCompanyDatasetIngestionService,
)
from backend.app.models import JobStatus
from shared.ai_engine.contracts import TenantContext


class _ScalarSequence:
    def __init__(self, *values):
        self.values = iter(values)

    def scalar(self, statement):
        return next(self.values)


class _DispatchRecorder:
    def __init__(self):
        self.generations = []

    def dispatch(self, tenant, dataset, *, dataset_generation):
        self.generations.append(dataset_generation)


def _automatic_service(*scalar_values):
    service = object.__new__(AutomaticCompanyDatasetIngestionService)
    service._dispatch_training = True
    service._session = _ScalarSequence(*scalar_values)
    service._dispatcher = _DispatchRecorder()
    return service


def _generation_dataset(generation, historical_status=JobStatus.COMPLETED):
    return type(
        "DatasetStub",
        (),
        {
            "id": uuid4(),
            "versions": [type("Version", (), {"is_current": True, "version_number": generation})()],
            "training_jobs": [type("Job", (), {"status": historical_status})()],
        },
    )()


def test_historical_completed_job_does_not_block_new_generation() -> None:
    service = _automatic_service(None, None)
    assert service._dispatch_training_safely(
        TenantContext(company_id=uuid4()), _generation_dataset(2)
    )
    assert service._dispatcher.generations == [2]


def test_active_or_completed_same_generation_blocks_duplicate() -> None:
    active_service = _automatic_service(uuid4())
    assert active_service._dispatch_training_safely(
        TenantContext(company_id=uuid4()), _generation_dataset(2, JobStatus.RUNNING)
    )
    assert active_service._dispatcher.generations == []

    completed_service = _automatic_service(None, uuid4())
    assert completed_service._dispatch_training_safely(
        TenantContext(company_id=uuid4()), _generation_dataset(2)
    )
    assert completed_service._dispatcher.generations == []


def test_medium_type_compatible_mapping_is_auto_accepted() -> None:
    assert AutomaticCompanyDatasetIngestionService._should_auto_accept(
        {
            "confidence": "medium",
            "score": 0.82,
            "reason": "Similarité de nom et type compatible.",
        }
    )


def test_low_but_compatible_mapping_can_be_auto_accepted() -> None:
    assert AutomaticCompanyDatasetIngestionService._should_auto_accept(
        {
            "confidence": "low",
            "score": 0.72,
            "reason": "Similarité de nom (0.72) et type compatible.",
        }
    )


def test_type_incompatible_mapping_is_never_auto_accepted() -> None:
    assert not AutomaticCompanyDatasetIngestionService._should_auto_accept(
        {
            "confidence": "low",
            "score": 0.96,
            "reason": "Nom proche mais type détecté incompatible : nécessite une revue.",
        }
    )


def test_unresolved_mapping_is_never_auto_accepted() -> None:
    assert not AutomaticCompanyDatasetIngestionService._should_auto_accept(
        {
            "confidence": "unresolved",
            "score": 0.40,
            "reason": "Aucune correspondance suffisante.",
        }
    )


def test_duplicate_safe_candidates_require_customer_confirmation() -> None:
    conflicts = AutomaticCompanyDatasetIngestionService._mapping_conflicts(
        {
            "transaction_total": "total_amount",
            "gross_amount": "total_amount",
            "checkout_id": "order_id",
        }
    )

    assert conflicts == [
        {
            "canonical_field": "total_amount",
            "columns": ["gross_amount", "transaction_total"],
        }
    ]


def test_unique_safe_candidates_do_not_require_confirmation() -> None:
    assert AutomaticCompanyDatasetIngestionService._mapping_conflicts(
        {"payment_value": "total_amount", "checkout_id": "order_id"}
    ) == []


def test_canonicalize_rows_preserves_originals_and_adds_canonical_aliases() -> None:
    rows = [
        {
            "client_ref": "C-1",
            "sale_date": "2026-08-27",
            "units": 3,
            "custom_note": "keep me",
        }
    ]
    mapping = {
        "client_ref": "customer_id",
        "sale_date": "order_timestamp",
        "units": "quantity",
    }

    result = AutomaticCompanyDatasetIngestionService._canonicalize_rows(rows, mapping)

    assert result == [
        {
            "client_ref": "C-1",
            "sale_date": "2026-08-27",
            "units": 3,
            "custom_note": "keep me",
            "customer_id": "C-1",
            "order_timestamp": "2026-08-27",
            "quantity": 3,
        }
    ]
