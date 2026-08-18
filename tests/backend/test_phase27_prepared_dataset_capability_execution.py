"""Phase 27 — Prepared Dataset → RetailSenseAI Capability Execution.

Aucune logique Olist : toutes les données utilisées ci-dessous sont
génériques et fictives (mêmes deux entreprises fictives que Phase 26, avec
des noms de colonnes totalement différents), pour prouver que chaque
capacité RetailSenseAI ne dépend jamais des noms de colonnes originaux du
client, uniquement des concepts canoniques (`customer_id`, `order_id`,
`product_id`, `order_timestamp`, `quantity`, `unit_price`, `total_amount`,
`review_text`, `review_score`).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.datasets import (
    get_capability_execution_gate,
    get_company_dataset_ingestion_service,
)
from backend.app.models import Base, Company, CompanyModule, CompanyModuleStatus, Module
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.capability_execution_gate import (
    CapabilityExecutionGate,
    prepare_training_input,
)
from backend.app.services.company_dataset_ingestion_service import (
    CompanyDatasetIngestionService,
    DatasetNotFoundError,
)
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from shared.ai_engine.capability_dataset.adapter import CapabilityDatasetAdapter
from shared.ai_engine.capability_dataset.contracts import CapabilityDataset, CapabilityDatasetValidation
from shared.ai_engine.capability_dataset.exceptions import (
    CAPABILITY_LABELS,
    InvalidCapabilityDataset,
    MissingCapabilityFields,
    UnknownCapability,
)
from shared.ai_engine.capability_dataset.feature_engineering import (
    CustomerRFMFeatures,
    compute_segmentation_rfm_features,
)
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.capability_requirements import CAPABILITY_DATA_REQUIREMENTS
from shared.ai_engine.dataset_ingestion.cleaning import CompanyDatasetCleaner
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset
from shared.ai_engine.dataset_ingestion.profiling import DatasetProfiler
from shared.ai_engine.dataset_ingestion.quality import assess_quality
from shared.ai_engine.dataset_ingestion.readiness import assess_capability_readiness
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage

# ---------------------------------------------------------------------------
# Test data — two realistic companies, no shared column names, no Olist terms
# ---------------------------------------------------------------------------

COMPANY_A_CSV = (
    b"client_ref,sale_number,item_code,sale_date,units,amount_paid,feedback_message,rating\n"
    b"C1,S1,P1,2024-01-01,3,$45.99,Great product fast delivery,5\n"
    b"C2,S2,P2,2024-01-02,1,$12.50,Not bad,3\n"
    b"C3,S3,P3,2024-01-03,2,$60.00,Average experience overall,4\n"
    b"C4,S4,P4,2024-01-04,4,$18.20,Loved the packaging,5\n"
)

COMPANY_B_ROWS = [
    {
        "buyer_uuid": "B1", "transaction_ref": "T1", "product_sku": "SKU1",
        "purchased_at": "2024-02-01", "quantity_ordered": 2, "revenue": 88.20,
        "customer_comment": "Loved it, will buy again", "stars": 4,
    },
    {
        "buyer_uuid": "B2", "transaction_ref": "T2", "product_sku": "SKU2",
        "purchased_at": "2024-02-02", "quantity_ordered": 5, "revenue": 210.0,
        "customer_comment": "Could be better honestly", "stars": 2,
    },
    {
        "buyer_uuid": "B3", "transaction_ref": "T3", "product_sku": "SKU3",
        "purchased_at": "2024-02-03", "quantity_ordered": 1, "revenue": 15.5,
        "customer_comment": "Perfectly fine purchase", "stars": 3,
    },
]

# Concepts génériques réellement requis par au moins une capacité RetailSenseAI
# (voir `CAPABILITY_DATA_REQUIREMENTS`). Aucun champ Olist (`customer_unique_id`,
# `order_purchase_timestamp`, `review_comment_message`, `freight_value`) n'y figure.
ALL_CAPABILITIES = tuple(CAPABILITY_DATA_REQUIREMENTS)


def _prepared_dataset(
    canonical_columns: dict[str, str],
    rows: list[dict[str, object]],
    company_id: UUID | None = None,
    dataset_id: UUID | None = None,
    version: int = 1,
) -> PreparedCompanyDataset:
    """Construit un `PreparedCompanyDataset` réel (même pipeline que le
    service de production), sans passer par HTTP/DB — pour des tests unitaires
    déterministes de `CapabilityDatasetAdapter`."""

    cleaner = CompanyDatasetCleaner()
    profiler = DatasetProfiler()
    cleaned_rows, cleaning_report = cleaner.clean(rows, canonical_columns)
    columns = tuple(dict.fromkeys(key for row in rows for key in row)) if rows else ()
    profile = profiler.profile(cleaned_rows, columns)
    quality = assess_quality(cleaning_report)
    readiness = assess_capability_readiness(set(canonical_columns.values()))
    return PreparedCompanyDataset(
        company_id=company_id or uuid4(),
        dataset_id=dataset_id or uuid4(),
        version=version,
        canonical_columns=canonical_columns,
        rows=tuple(cleaned_rows),
        profile=profile,
        mapping=(),
        cleaning_report=cleaning_report,
        quality=quality,
        capability_readiness=readiness,
    )


# Toutes les colonnes originales portent déjà les noms canoniques : sert de
# base "tout est prêt" pour la plupart des tests de capacité.
_FULL_CANONICAL_COLUMNS = {
    field: field
    for field in (
        "customer_id", "order_id", "product_id", "order_timestamp",
        "quantity", "total_amount", "review_text", "review_score",
    )
}


def _full_rows(count: int = 5) -> list[dict[str, object]]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "customer_id": f"cust-{i}",
            "order_id": f"order-{i}",
            "product_id": f"prod-{i % 3}",
            "order_timestamp": (base + timedelta(days=i)).isoformat(),
            "quantity": i + 1,
            "total_amount": 10.5 * (i + 1),
            "review_text": "Great service, would buy again" if i % 2 == 0 else "Mediocre experience",
            "review_score": 5 if i % 2 == 0 else 2,
        }
        for i in range(count)
    ]


# Style "Company A" : mêmes concepts, noms de colonnes originaux totalement
# différents et non-canoniques (mais pas Olist) — prouve la généricité.
_COMPANY_STYLE_CANONICAL_COLUMNS = {
    "client_ref": "customer_id",
    "sale_number": "order_id",
    "item_code": "product_id",
    "sale_date": "order_timestamp",
    "units": "quantity",
    "amount_paid": "total_amount",
    "feedback_message": "review_text",
    "rating": "review_score",
}


def _company_style_rows(count: int = 5) -> list[dict[str, object]]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "client_ref": f"C{i}",
            "sale_number": f"S{i}",
            "item_code": f"P{i % 3}",
            "sale_date": (base + timedelta(days=i)).isoformat(),
            "units": i + 1,
            "amount_paid": 20.0 * (i + 1),
            "feedback_message": "Loved the packaging" if i % 2 == 0 else "Not great honestly",
            "rating": 5 if i % 2 == 0 else 2,
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# 1. Capability preparation — ready cases (9 capabilities)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("capability", ALL_CAPABILITIES)
def test_prepare_capability_dataset_ready_cases(capability: str) -> None:
    """Toutes les capacités sauf `price` sont exécutables avec les concepts
    canoniques génériques (ni `unit_price` ni concept Olist n'est requis)."""

    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows())
    adapter = CapabilityDatasetAdapter()

    if capability == "price":
        with pytest.raises(MissingCapabilityFields) as exc_info:
            adapter.prepare(prepared, capability)
        assert "unit price" in str(exc_info.value)
        return

    capability_dataset = adapter.prepare(prepared, capability)
    assert isinstance(capability_dataset, CapabilityDataset)
    assert capability_dataset.capability == capability
    assert capability_dataset.required_fields == CAPABILITY_DATA_REQUIREMENTS[capability]
    assert capability_dataset.row_count == len(prepared.rows)
    assert capability_dataset.adapter_version == "1.0"
    assert not capability_dataset.warnings


def test_prepare_price_missing_unit_price_is_business_error() -> None:
    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows())
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields) as exc_info:
        adapter.prepare(prepared, "price")

    message = str(exc_info.value)
    assert message == "Price analysis requires unit price."
    assert "pandas" not in message.lower()
    assert "sklearn" not in message.lower()
    assert "keyerror" not in message.lower()


# ---------------------------------------------------------------------------
# 2. Missing-field business validation (before ML errors) — section 35
# ---------------------------------------------------------------------------


def test_sentiment_without_review_text_raises_before_ml() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "review_text"}
    prepared = _prepared_dataset(columns, [{k: v for k, v in row.items() if k != "review_text"} for row in _full_rows()])
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields) as exc_info:
        adapter.prepare(prepared, "sentiment")
    assert str(exc_info.value) == "Sentiment analysis requires customer feedback text."


def test_bad_review_without_review_text_raises_before_ml() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "review_text"}
    rows = [{k: v for k, v in row.items() if k != "review_text"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields):
        adapter.prepare(prepared, "bad_review")


def test_recommendation_without_customer_concept_raises() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "customer_id"}
    rows = [{k: v for k, v in row.items() if k != "customer_id"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields) as exc_info:
        adapter.prepare(prepared, "recommendation")
    assert "customer identifier" in str(exc_info.value)


def test_recommendation_without_product_concept_raises() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "product_id"}
    rows = [{k: v for k, v in row.items() if k != "product_id"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields) as exc_info:
        adapter.prepare(prepared, "recommendation")
    assert "product identifier" in str(exc_info.value)


def test_churn_without_order_timestamp_raises() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "order_timestamp"}
    rows = [{k: v for k, v in row.items() if k != "order_timestamp"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields) as exc_info:
        adapter.prepare(prepared, "churn")
    assert "Customer churn prediction" in str(exc_info.value)


def test_demand_without_temporal_data_raises() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "order_timestamp"}
    rows = [{k: v for k, v in row.items() if k != "order_timestamp"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields):
        adapter.prepare(prepared, "demand")


def test_demand_without_quantity_raises() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "quantity"}
    rows = [{k: v for k, v in row.items() if k != "quantity"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields):
        adapter.prepare(prepared, "demand")


def test_weekly_forecast_without_timestamp_raises() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "order_timestamp"}
    rows = [{k: v for k, v in row.items() if k != "order_timestamp"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields):
        adapter.prepare(prepared, "weekly_forecast")


def test_anomaly_without_quantity_raises() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "quantity"}
    rows = [{k: v for k, v in row.items() if k != "quantity"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields):
        adapter.prepare(prepared, "anomaly")


def test_segmentation_without_quantity_raises() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "quantity"}
    rows = [{k: v for k, v in row.items() if k != "quantity"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields):
        adapter.prepare(prepared, "segmentation")


# ---------------------------------------------------------------------------
# 3. Non-throwing validation (readiness) — section 15
# ---------------------------------------------------------------------------


def test_validate_never_raises_for_missing_fields() -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "review_text"}
    rows = [{k: v for k, v in row.items() if k != "review_text"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    validation = adapter.validate(prepared, "sentiment")
    assert isinstance(validation, CapabilityDatasetValidation)
    assert validation.ready is False
    assert validation.missing_fields == ("review_text",)
    assert validation.usable_row_count == 0
    assert validation.row_count == len(prepared.rows)


def test_validate_ready_true_when_all_requirements_met() -> None:
    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows())
    adapter = CapabilityDatasetAdapter()

    validation = adapter.validate(prepared, "churn")
    assert validation.ready is True
    assert validation.missing_fields == ()
    assert validation.usable_row_count == len(prepared.rows)


# ---------------------------------------------------------------------------
# 4. Dataset invalid vs. capability unavailable — section 32
# ---------------------------------------------------------------------------


def test_invalid_capability_dataset_when_mapped_but_empty_values() -> None:
    """`customer_id`/`order_timestamp` sont mappés mais toutes les valeurs
    sont vides : la capacité doit rester détectée comme non exploitable
    (`InvalidCapabilityDataset`), sans confondre avec un dataset invalide."""

    rows = [{"customer_id": None, "order_timestamp": None} for _ in range(3)]
    prepared = _prepared_dataset({"customer_id": "customer_id", "order_timestamp": "order_timestamp"}, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(InvalidCapabilityDataset):
        adapter.prepare(prepared, "churn")


def test_dataset_not_failed_when_one_capability_not_ready() -> None:
    """Un dataset global READY (`churn` prêt) ne doit pas être bloqué parce
    qu'une AUTRE capacité (`sentiment`) manque de données (section 32)."""

    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != "review_text"}
    rows = [{k: v for k, v in row.items() if k != "review_text"} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    churn_dataset = adapter.prepare(prepared, "churn")
    assert churn_dataset.capability == "churn"

    sentiment_validation = adapter.validate(prepared, "sentiment")
    assert sentiment_validation.ready is False


# ---------------------------------------------------------------------------
# 5. Unknown / future capabilities — sections 16, 29
# ---------------------------------------------------------------------------


def test_unknown_capability_raises() -> None:
    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows())
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(UnknownCapability):
        adapter.prepare(prepared, "not_a_real_capability")


def test_synthetic_data_is_not_a_registered_capability() -> None:
    assert "synthetic_data" not in CAPABILITY_DATA_REQUIREMENTS
    assert "synthetic_data" not in CAPABILITY_LABELS

    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows())
    adapter = CapabilityDatasetAdapter()
    with pytest.raises(UnknownCapability):
        adapter.prepare(prepared, "synthetic_data")


def test_all_nine_capabilities_registered_exactly() -> None:
    assert set(ALL_CAPABILITIES) == {
        "churn", "demand", "price", "segmentation", "recommendation",
        "sentiment", "bad_review", "anomaly", "weekly_forecast",
    }
    assert len(ALL_CAPABILITIES) == 9


# ---------------------------------------------------------------------------
# 6. Provenance, determinism, zero-copy — sections 23, 24, 3
# ---------------------------------------------------------------------------


def test_capability_dataset_preserves_provenance() -> None:
    company_id = uuid4()
    dataset_id = uuid4()
    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows(), company_id=company_id, dataset_id=dataset_id, version=3)
    adapter = CapabilityDatasetAdapter()

    capability_dataset = adapter.prepare(prepared, "churn")
    assert capability_dataset.company_id == company_id
    assert capability_dataset.dataset_id == dataset_id
    assert capability_dataset.dataset_version == 3
    assert capability_dataset.capability == "churn"
    assert capability_dataset.adapter_version == "1.0"


def test_capability_dataset_rows_are_not_copied() -> None:
    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows())
    adapter = CapabilityDatasetAdapter()

    capability_dataset = adapter.prepare(prepared, "churn")
    assert capability_dataset.rows is prepared.rows


def test_determinism_same_input_produces_same_output() -> None:
    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows())
    adapter = CapabilityDatasetAdapter()

    first = adapter.prepare(prepared, "segmentation")
    second = adapter.prepare(prepared, "segmentation")
    assert first == second


# ---------------------------------------------------------------------------
# 7. No Olist runtime dependency — section 38
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "capability",
    [c for c in ALL_CAPABILITIES if c != "price"],
)
def test_capability_works_without_olist_style_fields(capability: str) -> None:
    """Utilise des noms de colonnes clients complètement différents des
    canoniques (style Company A) — jamais `customer_unique_id`,
    `order_purchase_timestamp`, `review_comment_message`, ni `freight_value`."""

    prepared = _prepared_dataset(_COMPANY_STYLE_CANONICAL_COLUMNS, _company_style_rows())
    for original_column in prepared.canonical_columns:
        assert original_column not in {
            "customer_unique_id", "order_purchase_timestamp",
            "review_comment_message", "freight_value",
        }

    adapter = CapabilityDatasetAdapter()
    capability_dataset = adapter.prepare(prepared, capability)
    assert capability_dataset.capability == capability


# ---------------------------------------------------------------------------
# 8. No raw bypass — section 19/39
# ---------------------------------------------------------------------------


def test_adapter_prepare_only_accepts_prepared_company_dataset() -> None:
    """`CapabilityDatasetAdapter.prepare` n'accepte qu'un `PreparedCompanyDataset` :
    aucun paramètre de type chemin de fichier, DataFrame ou octets bruts."""

    import inspect

    signature = inspect.signature(CapabilityDatasetAdapter.prepare)
    parameter_names = set(signature.parameters) - {"self"}
    assert parameter_names == {"prepared", "capability"}
    annotation = signature.parameters["prepared"].annotation
    assert "PreparedCompanyDataset" in str(annotation)


def test_gate_prepare_signature_has_no_raw_bypass() -> None:
    import inspect

    signature = inspect.signature(CapabilityExecutionGate.prepare)
    parameter_names = set(signature.parameters) - {"self"}
    assert parameter_names == {"tenant", "dataset_id", "capability"}


# ---------------------------------------------------------------------------
# 9. Feature engineering boundary — section 21
# ---------------------------------------------------------------------------


def test_segmentation_rfm_features_are_derived_not_canonical() -> None:
    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows(6))
    adapter = CapabilityDatasetAdapter()
    capability_dataset = adapter.prepare(prepared, "segmentation")

    features = compute_segmentation_rfm_features(capability_dataset)
    assert len(features) > 0
    assert all(isinstance(f, CustomerRFMFeatures) for f in features)
    for feature in features:
        assert feature.frequency >= 1
        assert feature.monetary >= 0
        assert feature.recency_days >= 0
    # Les features dérivées ne font jamais partie du vocabulaire canonique.
    from shared.ai_engine.dataset_ingestion.canonical_fields import CANONICAL_FIELDS

    assert "recency_days" not in CANONICAL_FIELDS
    assert "frequency" not in CANONICAL_FIELDS
    assert "monetary" not in CANONICAL_FIELDS


def test_segmentation_rfm_rejects_other_capabilities() -> None:
    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows())
    adapter = CapabilityDatasetAdapter()
    capability_dataset = adapter.prepare(prepared, "churn")

    with pytest.raises(ValueError):
        compute_segmentation_rfm_features(capability_dataset)


def test_segmentation_rfm_deterministic() -> None:
    prepared = _prepared_dataset(_FULL_CANONICAL_COLUMNS, _full_rows(4))
    adapter = CapabilityDatasetAdapter()
    capability_dataset = adapter.prepare(prepared, "segmentation")

    first = compute_segmentation_rfm_features(capability_dataset)
    second = compute_segmentation_rfm_features(capability_dataset)
    assert first == second


# ---------------------------------------------------------------------------
# 10. Business-language exceptions — section 16
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "capability,forbidden_field,expected_missing_label",
    [
        ("sentiment", "review_text", "customer feedback text"),
        ("bad_review", "review_text", "customer feedback text"),
        ("churn", "order_timestamp", "order date/time"),
        ("segmentation", "quantity", "quantity sold"),
    ],
)
def test_missing_field_error_uses_business_language(
    capability: str, forbidden_field: str, expected_missing_label: str
) -> None:
    columns = {k: v for k, v in _FULL_CANONICAL_COLUMNS.items() if v != forbidden_field}
    rows = [{k: v for k, v in row.items() if k != forbidden_field} for row in _full_rows()]
    prepared = _prepared_dataset(columns, rows)
    adapter = CapabilityDatasetAdapter()

    with pytest.raises(MissingCapabilityFields) as exc_info:
        adapter.prepare(prepared, capability)
    message = str(exc_info.value)
    assert expected_missing_label in message
    for forbidden_term in ("pandas", "sklearn", "tensorflow", "dataframe", "keyerror", "nan"):
        assert forbidden_term not in message.lower()


# ---------------------------------------------------------------------------
# 11. HTTP integration — CapabilityExecutionGate, tenant isolation, API
# ---------------------------------------------------------------------------


@pytest.fixture
def phase27_environment(
    tmp_path: Path,
) -> Generator[tuple[TestClient, sessionmaker[Session], dict], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase27.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with session_factory() as session:
        companies = [
            Company(
                name=name, slug=slug, email=email, country="Canada",
                timezone="America/Toronto", industry="Retail",
                subscription_plan="professional",
            )
            for name, slug, email in (
                ("Company A", "phase27-company-a", "a27@example.ca"),
                ("Company B", "phase27-company-b", "b27@example.ca"),
            )
        ]
        module = Module(name="RetailSenseAI", code="retail", is_active=True)
        session.add_all([*companies, module])
        session.flush()
        now = datetime.now(timezone.utc)
        session.add_all([
            CompanyModule(
                company_id=company.id, module_id=module.id,
                activated_at=now - timedelta(minutes=1),
                status=CompanyModuleStatus.ACTIVE,
            )
            for company in companies
        ])
        session.commit()
        tenants = {
            "company_a": TenantContext(companies[0].id),
            "company_b": TenantContext(companies[1].id),
        }

    current = {"tenant": tenants["company_a"]}
    artifact_root = tmp_path / "artifacts"
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_ingestion_service() -> Generator[CompanyDatasetIngestionService, None, None]:
        with session_factory() as session:
            yield CompanyDatasetIngestionService(
                session=session,
                storage=LocalDatasetStorage(artifact_root / "company_datasets"),
                access=ModuleAccessService(SQLAlchemyModuleEntitlements(session)),
                max_upload_bytes=5 * 1024 * 1024,
            )

    def override_gate() -> Generator[CapabilityExecutionGate, None, None]:
        with session_factory() as session:
            service = CompanyDatasetIngestionService(
                session=session,
                storage=LocalDatasetStorage(artifact_root / "company_datasets"),
                access=ModuleAccessService(SQLAlchemyModuleEntitlements(session)),
                max_upload_bytes=5 * 1024 * 1024,
            )
            yield CapabilityExecutionGate(service)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: current["tenant"]
    app.dependency_overrides[get_company_dataset_ingestion_service] = override_ingestion_service
    app.dependency_overrides[get_capability_execution_gate] = override_gate
    with TestClient(app) as client:
        yield client, session_factory, {**tenants, "current": current, "artifact_root": artifact_root}


def _upload(client: TestClient, filename: str, content: bytes, content_type: str = "text/csv"):
    return client.post(
        "/api/v1/datasets/upload",
        data={"module_code": "retail"},
        files={"file": (filename, content, content_type)},
    )


def test_api_prepare_churn_ready_company_a(phase27_environment) -> None:
    client, _, _ = phase27_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]

    response = client.post(f"/api/v1/datasets/{dataset_id}/capabilities/churn/prepare")
    assert response.status_code == 200
    body = response.json()
    assert body["capability"] == "churn"
    assert body["dataset_id"] == dataset_id
    assert body["row_count"] == 4
    assert body["adapter_version"] == "1.0"


@pytest.mark.parametrize(
    "capability",
    ["churn", "segmentation", "recommendation", "sentiment", "demand", "weekly_forecast", "bad_review", "anomaly"],
)
def test_api_prepare_ready_capabilities_company_a(phase27_environment, capability: str) -> None:
    client, _, _ = phase27_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]

    response = client.post(f"/api/v1/datasets/{dataset_id}/capabilities/{capability}/prepare")
    assert response.status_code == 200
    assert response.json()["capability"] == capability


def test_api_prepare_price_missing_unit_price_returns_business_error(phase27_environment) -> None:
    client, _, _ = phase27_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]

    response = client.post(f"/api/v1/datasets/{dataset_id}/capabilities/price/prepare")
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Price analysis requires unit price."


def test_api_prepare_unknown_capability_returns_400(phase27_environment) -> None:
    client, _, _ = phase27_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]

    response = client.post(f"/api/v1/datasets/{dataset_id}/capabilities/not_real/prepare")
    assert response.status_code == 400


def test_api_prepare_company_b_generic_columns_also_works(phase27_environment) -> None:
    import json

    client, _, tenants = phase27_environment
    tenants["current"]["tenant"] = tenants["company_b"]
    dataset_id = _upload(
        client, "company_b.json", json.dumps(COMPANY_B_ROWS).encode("utf-8"), content_type="application/json"
    ).json()["dataset_id"]

    response = client.post(f"/api/v1/datasets/{dataset_id}/capabilities/sentiment/prepare")
    assert response.status_code == 200
    assert response.json()["capability"] == "sentiment"


# ---------------------------------------------------------------------------
# 12. Cross-tenant security — section 18, 37
# ---------------------------------------------------------------------------


def test_company_a_cannot_prepare_company_b_dataset(phase27_environment) -> None:
    import json

    client, _, tenants = phase27_environment
    tenants["current"]["tenant"] = tenants["company_b"]
    dataset_b_id = _upload(
        client, "company_b.json", json.dumps(COMPANY_B_ROWS).encode("utf-8"), content_type="application/json"
    ).json()["dataset_id"]

    tenants["current"]["tenant"] = tenants["company_a"]
    response = client.post(f"/api/v1/datasets/{dataset_b_id}/capabilities/churn/prepare")
    assert response.status_code == 404


def test_company_b_cannot_prepare_company_a_dataset(phase27_environment) -> None:
    client, _, tenants = phase27_environment
    dataset_a_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]

    tenants["current"]["tenant"] = tenants["company_b"]
    response = client.post(f"/api/v1/datasets/{dataset_a_id}/capabilities/churn/prepare")
    assert response.status_code == 404


def test_gate_direct_cross_tenant_a_dataset_b_refused(phase27_environment) -> None:
    client, session_factory, tenants = phase27_environment
    import json

    tenants["current"]["tenant"] = tenants["company_b"]
    dataset_b_id = UUID(
        _upload(
            client, "company_b.json", json.dumps(COMPANY_B_ROWS).encode("utf-8"), content_type="application/json"
        ).json()["dataset_id"]
    )

    with session_factory() as session:
        service = CompanyDatasetIngestionService(
            session=session,
            storage=LocalDatasetStorage(tenants["artifact_root"] / "company_datasets"),
            access=ModuleAccessService(SQLAlchemyModuleEntitlements(session)),
            max_upload_bytes=5 * 1024 * 1024,
        )
        gate = CapabilityExecutionGate(service)
        with pytest.raises(DatasetNotFoundError):
            gate.prepare(tenants["company_a"], dataset_b_id, "churn")


def test_gate_direct_cross_tenant_b_dataset_a_refused(phase27_environment) -> None:
    client, session_factory, tenants = phase27_environment
    dataset_a_id = UUID(_upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"])

    with session_factory() as session:
        service = CompanyDatasetIngestionService(
            session=session,
            storage=LocalDatasetStorage(tenants["artifact_root"] / "company_datasets"),
            access=ModuleAccessService(SQLAlchemyModuleEntitlements(session)),
            max_upload_bytes=5 * 1024 * 1024,
        )
        gate = CapabilityExecutionGate(service)
        with pytest.raises(DatasetNotFoundError):
            gate.prepare(tenants["company_b"], dataset_a_id, "churn")


def test_gate_direct_same_tenant_own_dataset_succeeds(phase27_environment) -> None:
    client, session_factory, tenants = phase27_environment
    dataset_a_id = UUID(_upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"])

    with session_factory() as session:
        service = CompanyDatasetIngestionService(
            session=session,
            storage=LocalDatasetStorage(tenants["artifact_root"] / "company_datasets"),
            access=ModuleAccessService(SQLAlchemyModuleEntitlements(session)),
            max_upload_bytes=5 * 1024 * 1024,
        )
        gate = CapabilityExecutionGate(service)
        capability_dataset = gate.prepare(tenants["company_a"], dataset_a_id, "churn")
        assert capability_dataset.company_id == tenants["company_a"].company_id


# ---------------------------------------------------------------------------
# 13. Training handoff — section 20
# ---------------------------------------------------------------------------


def test_prepare_training_input_returns_capability_dataset(phase27_environment) -> None:
    client, session_factory, tenants = phase27_environment
    dataset_a_id = UUID(_upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"])

    with session_factory() as session:
        service = CompanyDatasetIngestionService(
            session=session,
            storage=LocalDatasetStorage(tenants["artifact_root"] / "company_datasets"),
            access=ModuleAccessService(SQLAlchemyModuleEntitlements(session)),
            max_upload_bytes=5 * 1024 * 1024,
        )
        gate = CapabilityExecutionGate(service)
        result = prepare_training_input(gate, tenants["company_a"], dataset_a_id, "demand")
        assert isinstance(result, CapabilityDataset)
        assert result.capability == "demand"


# ---------------------------------------------------------------------------
# 14. Regression — Phase 26 endpoints remain unaffected (section 42)
# ---------------------------------------------------------------------------


def test_phase26_profile_endpoint_still_reports_capability_readiness(phase27_environment) -> None:
    client, _, _ = phase27_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]

    response = client.get(f"/api/v1/datasets/{dataset_id}/profile")
    assert response.status_code == 200
    readiness = {item["capability"]: item["ready"] for item in response.json()["capability_readiness"]}
    assert readiness["churn"] is True
    assert readiness["price"] is False


def test_phase26_upload_still_returns_201(phase27_environment) -> None:
    client, _, _ = phase27_environment
    response = _upload(client, "company_a.csv", COMPANY_A_CSV)
    assert response.status_code == 201
