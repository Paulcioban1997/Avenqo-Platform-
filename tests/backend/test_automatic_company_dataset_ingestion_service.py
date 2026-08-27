from __future__ import annotations

from backend.app.services.automatic_company_dataset_ingestion_service import (
    AutomaticCompanyDatasetIngestionService,
)


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
