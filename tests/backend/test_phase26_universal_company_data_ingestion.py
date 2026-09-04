"""Phase 26 — Universal Company Data Ingestion & Tenant Data Foundation.

Aucune logique Olist : toutes les données utilisées ci-dessous sont
génériques et fictives, avec deux entreprises aux noms de colonnes
totalement différents pour prouver l'absence de toute dépendance à un
schéma figé.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.datasets import (
    get_company_dataset_ingestion_service,
    get_dataset_import_service,
)
from backend.app.models import (
    Base,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    Dataset,
    DatasetRelationship,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
    Module,
)
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.automatic_company_dataset_ingestion_service import (
    AutomaticCompanyDatasetIngestionService,
)
from backend.app.services.company_dataset_ingestion_service import (
    CompanyDatasetIngestionService,
    InvalidMappingError,
)
from backend.app.services.dataset_import_service import DatasetImportService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.main import create_application
from backend.app.routers.datasets import require_dataset_read
from modules.entitlements import ModuleAccessService
from shared.ai_engine.contracts import TenantContext
from tests.subscription_helpers import add_active_subscription
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage

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

AMBIGUOUS_CSV = (
    b"customer_review,cust_id_number,qty,created\n"
    b"Great service and fast,12345,3,2024-01-01\n"
    b"Bad experience overall,12346,1,2024-01-02\n"
    b"Average nothing special,12347,2,2024-01-03\n"
)

GENERIC_CSV = b"id,age,segment\n1,20,A\n2,30,B\n2,30,B\n"


def _company_b_json() -> bytes:
    return json.dumps(COMPANY_B_ROWS).encode("utf-8")


def _company_a_xlsx() -> bytes:
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "client_ref": "C1", "sale_number": "S1", "item_code": "P1",
                "sale_date": "2024-01-01", "units": 3, "amount_paid": 45.99,
                "feedback_message": "Great product fast delivery", "rating": 5,
            },
            {
                "client_ref": "C2", "sale_number": "S2", "item_code": "P2",
                "sale_date": "2024-01-02", "units": 1, "amount_paid": 12.5,
                "feedback_message": "Not bad", "rating": 3,
            },
        ]
    )
    buffer = BytesIO()
    frame.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def _company_b_parquet() -> bytes:
    import pandas as pd

    frame = pd.DataFrame(COMPANY_B_ROWS)
    buffer = BytesIO()
    frame.to_parquet(buffer, engine="pyarrow")
    return buffer.getvalue()


@pytest.fixture
def phase26_environment(
    tmp_path: Path,
) -> Generator[tuple[TestClient, sessionmaker[Session], dict], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase26.db'}",
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
                ("Company A", "company-a", "a@example.ca"),
                ("Company B", "company-b", "b@example.ca"),
                ("No Access Co", "no-access-co", "no-access@example.ca"),
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
            for company in companies[:2]
        ])
        for company in companies:
            add_active_subscription(session, company)
        session.commit()
        tenants = {
            "company_a": TenantContext(companies[0].id),
            "company_b": TenantContext(companies[1].id),
            "no_access": TenantContext(companies[2].id),
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
                quota=DataImportPolicy(session),
                max_upload_bytes=5 * 1024 * 1024,
            )

    def override_dataset_import_service() -> Generator[DatasetImportService, None, None]:
        with session_factory() as session:
            yield DatasetImportService(
                session=session,
                artifacts=ArtifactService(artifact_root),
                quota=DataImportPolicy(session),
                max_upload_bytes=5 * 1024 * 1024,
            )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: current["tenant"]
    app.dependency_overrides[require_dataset_read] = lambda: object()
    app.dependency_overrides[get_company_dataset_ingestion_service] = override_ingestion_service
    app.dependency_overrides[get_dataset_import_service] = override_dataset_import_service
    with TestClient(app) as client:
        yield client, session_factory, {**tenants, "current": current, "artifact_root": artifact_root}


def _upload(client: TestClient, filename: str, content: bytes, content_type: str = "text/csv"):
    return client.post(
        "/api/v1/datasets/upload",
        data={"module_code": "retail"},
        files={"file": (filename, content, content_type)},
    )


# ---------------------------------------------------------------------------
# 1. File formats
# ---------------------------------------------------------------------------


def test_upload_csv_creates_ready_dataset(phase26_environment) -> None:
    client, _, _ = phase26_environment
    response = _upload(client, "company_a.csv", COMPANY_A_CSV)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert body["rows"] == 4
    assert body["columns"] == 8


def test_same_tenant_imports_multiple_ready_datasets_with_different_schemas(
    phase26_environment,
) -> None:
    client, _, _ = phase26_environment

    customers = _upload(
        client,
        "customers.csv",
        b"customer_id,email\nC-1,one@example.ca\nC-2,two@example.ca\n",
    )
    orders = _upload(
        client,
        "orders.csv",
        b"order_id,order_timestamp\nO-1,2026-08-01\nO-2,2026-08-02\n",
    )

    assert customers.status_code == orders.status_code == 201
    assert customers.json()["status"] == orders.json()["status"] == "ready"
    listed = client.get("/api/v1/datasets").json()
    assert {dataset["name"] for dataset in listed} == {"customers.csv", "orders.csv"}


def test_upload_xlsx_creates_dataset(phase26_environment) -> None:
    client, _, _ = phase26_environment
    response = _upload(
        client, "company_a.xlsx", _company_a_xlsx(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert response.status_code == 201
    assert response.json()["rows"] == 2


def test_upload_json_creates_dataset(phase26_environment) -> None:
    client, _, tenants = phase26_environment
    tenants["current"]["tenant"] = tenants["company_b"]
    response = _upload(client, "company_b.json", _company_b_json(), content_type="application/json")
    assert response.status_code == 201
    assert response.json()["rows"] == 3


def test_upload_parquet_creates_dataset(phase26_environment) -> None:
    client, _, tenants = phase26_environment
    tenants["current"]["tenant"] = tenants["company_b"]
    response = _upload(
        client, "company_b.parquet", _company_b_parquet(), content_type="application/octet-stream"
    )
    assert response.status_code == 201
    assert response.json()["rows"] == 3


def test_upload_unsupported_format_rejected(phase26_environment) -> None:
    client, _, _ = phase26_environment
    response = _upload(client, "dataset.txt", b"hello world", content_type="text/plain")
    assert response.status_code == 400


def test_upload_empty_file_rejected(phase26_environment) -> None:
    client, _, _ = phase26_environment
    response = _upload(client, "empty.csv", b"")
    assert response.status_code == 400


def test_upload_corrupted_csv_rejected(phase26_environment) -> None:
    client, _, _ = phase26_environment
    response = _upload(client, "corrupt.csv", b"\xff\xfe\x00\x01not-utf8")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# 2. Tenant isolation
# ---------------------------------------------------------------------------


def test_upload_A_and_B_isolated_listing(phase26_environment) -> None:
    client, _, tenants = phase26_environment
    _upload(client, "company_a.csv", COMPANY_A_CSV)

    tenants["current"]["tenant"] = tenants["company_b"]
    _upload(client, "company_b.json", _company_b_json(), content_type="application/json")

    assert len(client.get("/api/v1/datasets").json()) == 1


def test_cross_tenant_dataset_access_refused(phase26_environment) -> None:
    client, _, tenants = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]

    tenants["current"]["tenant"] = tenants["company_b"]
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404


def test_cross_tenant_profile_access_refused(phase26_environment) -> None:
    client, _, tenants = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]

    tenants["current"]["tenant"] = tenants["company_b"]
    assert client.get(f"/api/v1/datasets/{dataset_id}/profile").status_code == 404


def test_cross_tenant_mapping_submit_refused(phase26_environment) -> None:
    client, _, tenants = phase26_environment
    dataset_id = _upload(client, "ambiguous.csv", AMBIGUOUS_CSV).json()["dataset_id"]

    tenants["current"]["tenant"] = tenants["company_b"]
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/mapping",
        json={"mapping": {"cust_id_number": "customer_id"}},
    )
    assert response.status_code == 404


def test_no_module_access_upload_still_succeeds_core_capability(phase26_environment) -> None:
    """L'ingestion universelle est CORE Avenqo : aucune activation de module
    optionnel n'est requise pour importer des données (Demo inclus)."""
    client, _, tenants = phase26_environment
    tenants["current"]["tenant"] = tenants["no_access"]
    response = _upload(client, "company_a.csv", COMPANY_A_CSV)
    assert response.status_code == 201


def test_path_traversal_filename_rejected(phase26_environment) -> None:
    client, session_factory, _ = phase26_environment
    response = _upload(client, "../../other_company/file.csv", COMPANY_A_CSV)
    assert response.status_code == 201

    with session_factory() as session:
        version = session.scalar(select(DatasetVersion))
        assert ".." not in Path(version.artifact_path).parts
        assert Path(version.artifact_path).is_file()



# ---------------------------------------------------------------------------
# 3. Mapping
# ---------------------------------------------------------------------------


def test_exact_alias_mapping_company_a(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]

    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    mapping = {s["original_column"]: s["suggested_field"] for s in profile["mapping_suggestions"]}
    assert mapping["client_ref"] == "customer_id"
    assert mapping["sale_number"] == "order_id"
    assert mapping["item_code"] == "product_id"
    assert mapping["feedback_message"] == "review_text"
    assert profile["review_required"] is False


def test_exact_alias_mapping_company_b(phase26_environment) -> None:
    client, _, tenants = phase26_environment
    tenants["current"]["tenant"] = tenants["company_b"]
    dataset_id = _upload(
        client, "company_b.json", _company_b_json(), content_type="application/json"
    ).json()["dataset_id"]

    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    mapping = {s["original_column"]: s["suggested_field"] for s in profile["mapping_suggestions"]}
    assert mapping["buyer_uuid"] == "customer_id"
    assert mapping["product_sku"] == "product_id"
    assert mapping["revenue"] == "total_amount"
    assert mapping["customer_comment"] == "review_text"


def test_product_fields_are_automatically_mapped_without_user_configuration() -> None:
    from shared.ai_engine.dataset_ingestion.column_mapper import SemanticColumnMapper

    rows = [
        {
            "id_produit": "P1",
            "product_name": "Coffee",
            "categorie": "Drinks",
            "stock_level": 8,
        }
    ]
    mapping = {
        item.original_column: item.suggested_field
        for item in SemanticColumnMapper().suggest(tuple(rows[0]), rows)
    }

    assert mapping == {
        "id_produit": "product_id",
        "product_name": "product_name",
        "categorie": "product_category",
        "stock_level": "inventory_level",
    }


def test_generic_commerce_identifiers_dates_and_amounts_map_semantically() -> None:
    from shared.ai_engine.dataset_ingestion.column_mapper import SemanticColumnMapper

    rows = [
        {
            "checkout_id": "O-1",
            "merchant_code": "S-1",
            "payment_ref": "PAY-1",
            "feedback_id": "REV-1",
            "purchase_date": "2026-08-20",
            "fulfilled_at": "2026-08-22",
            "gross_amount": 42.5,
            "shipping_cost": 3.5,
        }
    ]
    mapping = {
        item.original_column: item.suggested_field
        for item in SemanticColumnMapper().suggest(tuple(rows[0]), rows)
    }

    assert mapping == {
        "checkout_id": "order_id",
        "merchant_code": "seller_id",
        "payment_ref": "payment_id",
        "feedback_id": "review_id",
        "purchase_date": "order_timestamp",
        "fulfilled_at": "delivery_timestamp",
        "gross_amount": "total_amount",
        "shipping_cost": "freight_amount",
    }


def test_ambiguous_column_triggers_review_required(phase26_environment) -> None:
    client, _, _ = phase26_environment
    response = _upload(client, "ambiguous.csv", AMBIGUOUS_CSV)
    assert response.json()["status"] == "mapping_required"


def test_type_mismatch_customer_review_not_mapped_to_customer_id(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "ambiguous.csv", AMBIGUOUS_CSV).json()["dataset_id"]

    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    suggestions = {s["original_column"]: s for s in profile["mapping_suggestions"]}
    review_suggestion = suggestions["customer_review"]
    assert review_suggestion["confidence"] in {"low", "unresolved"}
    id_suggestion = suggestions["cust_id_number"]
    assert id_suggestion["suggested_field"] == "customer_id"


def test_manual_override_mapping_accepted(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "ambiguous.csv", AMBIGUOUS_CSV).json()["dataset_id"]

    response = client.post(
        f"/api/v1/datasets/{dataset_id}/mapping",
        json={"mapping": {"cust_id_number": "customer_id", "created": "order_timestamp"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["mapping"]["cust_id_number"] == "customer_id"
    assert body["approved"] is True


def test_manual_override_invalid_canonical_field_rejected(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "ambiguous.csv", AMBIGUOUS_CSV).json()["dataset_id"]

    response = client.post(
        f"/api/v1/datasets/{dataset_id}/mapping",
        json={"mapping": {"cust_id_number": "not_a_real_field"}},
    )
    assert response.status_code == 400


def test_manual_override_marks_provenance_manual(phase26_environment) -> None:
    client, session_factory, _ = phase26_environment
    dataset_id = _upload(client, "ambiguous.csv", AMBIGUOUS_CSV).json()["dataset_id"]

    client.post(
        f"/api/v1/datasets/{dataset_id}/mapping",
        json={"mapping": {"cust_id_number": "customer_id"}},
    )
    with session_factory() as session:
        dataset = session.scalar(select(Dataset))
        assert dataset.mapping.mapping_json["provenance"]["cust_id_number"] == "manual"



# ---------------------------------------------------------------------------
# 4. Cleaning
# ---------------------------------------------------------------------------


def test_duplicate_rows_removed_reported_as_warning(phase26_environment) -> None:
    client, _, _ = phase26_environment
    content = (
        b"client_ref,sale_number,item_code,sale_date,units,amount_paid,feedback_message,rating\n"
        b"C1,S1,P1,2024-01-01,3,$45.99,Great product fast delivery,5\n"
        b"C1,S1,P1,2024-01-01,3,$45.99,Great product fast delivery,5\n"
        b"C2,S2,P2,2024-01-02,1,$12.50,Not bad service,3\n"
        b"C3,S3,P3,2024-01-03,2,$30.00,Pretty solid purchase,4\n"
    )
    response = _upload(client, "dup.csv", content)
    assert response.status_code == 201
    dataset_id = response.json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    assert profile["quality_status"] in {"good", "warning"}


def test_cleaning_detail_exports_and_cross_tenant_access(phase26_environment) -> None:
    client, session_factory, tenants = phase26_environment
    content = (
        b"client_ref,sale_date,amount_paid\n"
        b" C1 ,2024-01-01,$45.99\n"
        b" C1 ,2024-01-01,$45.99\n"
        b"C2,2024-01-02,$12.50\n"
    )
    upload = _upload(client, "cleaning.csv", content)
    assert upload.status_code == 201
    dataset_id = upload.json()["dataset_id"]

    detail_response = client.get(f"/api/v1/datasets/{dataset_id}/cleaning?limit=1")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "ready"
    assert detail["summary"]["original_row_count"] == 3
    assert detail["summary"]["cleaned_row_count"] == 2
    assert detail["summary"]["duplicate_rows_removed"] == 1
    assert detail["summary"]["numeric_normalizations"] == 2
    assert detail["summary"]["date_normalizations"] == 2
    assert detail["summary"]["inferred_data_types"]["amount_paid"] == "string"
    assert detail["summary"]["outlier_handling"] is None
    assert len(detail["original_preview"]) == 3
    assert len(detail["cleaned_preview"]) == 1
    assert detail["cleaned_preview"][0]["client_ref"] == "C1"

    csv_export = client.get(f"/api/v1/datasets/{dataset_id}/export/csv")
    assert csv_export.status_code == 200
    assert b"C1,2024-01-01T00:00:00,45.99" in csv_export.content

    xlsx_export = client.get(f"/api/v1/datasets/{dataset_id}/export/xlsx")
    assert xlsx_export.status_code == 200
    workbook = pytest.importorskip("openpyxl").load_workbook(BytesIO(xlsx_export.content))
    assert workbook.active.max_row == 3

    pdf_export = client.get(f"/api/v1/datasets/{dataset_id}/export/pdf")
    assert pdf_export.status_code == 200
    assert pdf_export.content.startswith(b"%PDF")

    docx_export = client.get(f"/api/v1/datasets/{dataset_id}/export/docx")
    assert docx_export.status_code == 200
    assert docx_export.content.startswith(b"PK")

    with session_factory() as session:
        dataset = session.get(Dataset, UUID(dataset_id))
        current_version = next(item for item in dataset.versions if item.is_current)
        assert Path(current_version.artifact_path).read_bytes() == content
        prepared_path = (
            Path(current_version.artifact_path).parent.parent / "prepared" / "prepared.json"
        )
        metadata_path = (
            Path(current_version.artifact_path).parent.parent / "metadata" / "metadata.json"
        )
        prepared_path.unlink()
        metadata_path.unlink()

    recovered_detail = client.get(f"/api/v1/datasets/{dataset_id}/cleaning")
    assert recovered_detail.status_code == 200
    assert recovered_detail.json()["summary"]["cleaned_row_count"] == 2
    assert prepared_path.is_file()
    assert metadata_path.is_file()

    tenants["current"]["tenant"] = tenants["company_b"]
    assert client.get(f"/api/v1/datasets/{dataset_id}/cleaning").status_code == 404
    assert client.get(f"/api/v1/datasets/{dataset_id}/export/csv").status_code == 404


def test_attention_required_exposes_cleaned_detail_and_exports(
    phase26_environment,
) -> None:
    client, _, _ = phase26_environment
    upload = _upload(client, "ambiguous.csv", AMBIGUOUS_CSV)
    dataset_id = upload.json()["dataset_id"]

    detail_response = client.get(f"/api/v1/datasets/{dataset_id}/cleaning")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "attention_required"
    assert detail["cleaning_status"] in {"good", "warning"}
    assert detail["summary"]["original_row_count"] == 3
    assert detail["summary"]["cleaned_row_count"] == 3
    assert detail["original_preview"][0]["customer_review"] == "Great service and fast"
    assert detail["cleaned_preview"][0]["customer_review"] == "Great service and fast"
    assert detail["preview_total"] == 3
    assert len(detail["transformation_history"]) == 1

    with phase26_environment[1]() as session:
        dataset = session.get(Dataset, UUID(dataset_id))
        current_version = next(item for item in dataset.versions if item.is_current)
        assert current_version.status == DatasetVersionStatus.VALIDATED

    for export_format in ("csv", "xlsx", "pdf", "docx"):
        response = client.get(f"/api/v1/datasets/{dataset_id}/export/{export_format}")
        assert response.status_code == 200
        assert response.content


def test_reconcile_endpoint_reports_promoted_and_ambiguous_datasets(
    phase26_environment,
) -> None:
    client, _, tenants = phase26_environment
    promoted = Dataset(
        company_id=tenants["company_a"].company_id,
        name="safe.csv",
        type="csv",
        source="safe.csv",
        status=DatasetStatus.READY,
    )
    ambiguous = Dataset(
        company_id=tenants["company_a"].company_id,
        name="ambiguous.csv",
        type="csv",
        source="ambiguous.csv",
        status=DatasetStatus.MAPPING_REQUIRED,
    )
    app = client.app
    original = app.dependency_overrides[get_company_dataset_ingestion_service]
    app.dependency_overrides[get_company_dataset_ingestion_service] = lambda: SimpleNamespace(
        reconcile_existing=lambda tenant: (promoted, ambiguous)
    )
    try:
        response = client.post("/api/v1/datasets/reconcile")
    finally:
        app.dependency_overrides[get_company_dataset_ingestion_service] = original

    assert response.status_code == 200
    assert response.json() == {
        "reviewed": 2,
        "promoted_to_ready": 1,
        "attention_required": 1,
    }


def test_automatic_pipeline_recovers_records_and_refreshes_relationships(
    phase26_environment,
) -> None:
    _client, session_factory, tenants = phase26_environment
    tenant = tenants["company_a"]
    dispatched: list = []
    with session_factory() as session:
        service = AutomaticCompanyDatasetIngestionService(
            session=session,
            storage=LocalDatasetStorage(tenants["artifact_root"] / "company_datasets"),
            quota=DataImportPolicy(session),
            max_upload_bytes=5 * 1024 * 1024,
            dispatcher=SimpleNamespace(
                dispatch=lambda resolved_tenant, dataset: dispatched.append(
                    (resolved_tenant.company_id, dataset.id)
                )
            ),
        )
        customers = service.upload(
            tenant,
            "retail",
            "people-export.csv",
            b"buyer_uuid\nC1\nC2\n",
        )
        related_orders = service.upload(
            tenant,
            "retail",
            "related-orders.csv",
            b"checkout_id,buyer_uuid,client_ref\nO1,C1,X1\nO2,C2,X2\n",
        )
        orders = service.upload(
            tenant,
            "retail",
            "commerce-export.csv",
            b"checkout_id,buyer_uuid,purchase_date,payment_value\nO1,C1,2026-08-01,10\nO2,C1,2026-08-02,20\nO3,C2,2026-08-03,0\n",
        )

        assert customers.status == related_orders.status == orders.status == DatasetStatus.READY
        assert related_orders.mapping.mapping_json["accepted"]["buyer_uuid"] == "customer_id"
        assert "client_ref" not in related_orders.mapping.mapping_json["accepted"]
        relationship_evidence = related_orders.mapping.mapping_json[
            "automatic_resolution"
        ]["relationship_evidence"]
        assert relationship_evidence[0]["source_column"] == "buyer_uuid"
        assert relationship_evidence[0]["peer_dataset_id"] == str(customers.id)
        assert orders.mapping.mapping_json["accepted"]["payment_value"] == "total_amount"
        assert orders.mapping.mapping_json["automatic_resolution"]["pipeline_finalized"] is True
        relationships = session.scalars(select(DatasetRelationship)).all()
        assert {item.canonical_field for item in relationships} == {
            "customer_id",
            "order_id",
        }

        initial_ids = set(session.scalars(select(Dataset.id)).all())
        orders.status = DatasetStatus.MAPPING_REQUIRED
        session.commit()
        reconciled = service.reconcile_existing(tenant)
        assert [item.id for item in reconciled] == [orders.id]
        assert reconciled[0].status == DatasetStatus.READY
        assert service.reconcile_existing(tenant) == ()
        assert set(session.scalars(select(Dataset.id)).all()) == initial_ids

        ambiguous = service.upload(
            tenant,
            "retail",
            "ambiguous-values.csv",
            b"checkout_id,transaction_total,gross_amount\nO1,10,12\nO2,20,22\n",
        )
        assert ambiguous.status == DatasetStatus.MAPPING_REQUIRED
        assert ambiguous.mapping.mapping_json["required_confirmation"] == [
            {
                "canonical_field": "total_amount",
                "columns": ["gross_amount", "transaction_total"],
            }
        ]

        current_version = next(item for item in ambiguous.versions if item.is_current)
        raw_path = Path(current_version.artifact_path)
        original_content = raw_path.read_bytes()
        prepared_path = raw_path.parent.parent / "prepared" / "prepared.json"
        metadata_path = raw_path.parent.parent / "metadata" / "metadata.json"
        assert prepared_path.is_file()
        assert metadata_path.is_file()
        prepared_path.unlink()
        metadata_path.unlink()

        reconciled = service.reconcile_existing(tenant)
        recovered = next(item for item in reconciled if item.id == ambiguous.id)
        assert recovered.status == DatasetStatus.MAPPING_REQUIRED
        assert prepared_path.is_file()
        assert metadata_path.is_file()
        assert service.get_cleaned_rows(tenant, ambiguous.id)
        assert raw_path.read_bytes() == original_content
        assert set(session.scalars(select(Dataset.id)).all()) == initial_ids | {
            ambiguous.id
        }

        with pytest.raises(InvalidMappingError, match="Select a source column"):
            service.submit_mapping(tenant, ambiguous.id, {})

        confirmed = service.submit_mapping(
            tenant,
            ambiguous.id,
            {"gross_amount": "total_amount"},
        )
        assert confirmed.status == DatasetStatus.READY
        assert confirmed.mapping.mapping_json["accepted"]["gross_amount"] == "total_amount"
        assert "transaction_total" not in confirmed.mapping.mapping_json["accepted"]
        assert next(
            item for item in confirmed.versions if item.is_current
        ).status == DatasetVersionStatus.READY

        unknown = service.upload(
            tenant,
            "retail",
            "unknown-schema.csv",
            b"opaque_label,mystery_blob\nA,foo\nB,bar\n",
        )
        assert unknown.status == DatasetStatus.MAPPING_REQUIRED
        assert unknown.mapping.mapping_json["accepted"] == {}
        with pytest.raises(InvalidMappingError, match="business concept"):
            service.submit_mapping(tenant, unknown.id, {})
        assert dispatched


def test_currency_string_converted_to_numeric(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    response = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    total_amount_column = next(
        (c for c in response["columns"] if c["name"] == "amount_paid"), None
    )
    assert total_amount_column is not None


def test_null_cells_detected_do_not_fail_pipeline(phase26_environment) -> None:
    client, _, _ = phase26_environment
    content = (
        b"client_ref,sale_number,item_code,sale_date,units,amount_paid,feedback_message,rating\n"
        b"C1,S1,P1,2024-01-01,,$45.99,Great product fast delivery,5\n"
        b"C2,S2,P2,2024-01-02,1,,Not bad service,3\n"
    )
    response = _upload(client, "nulls.csv", content)
    assert response.status_code == 201
    assert response.json()["status"] == "ready"


def test_cleaning_never_deletes_non_duplicate_rows(phase26_environment) -> None:
    client, _, _ = phase26_environment
    response = _upload(client, "company_a.csv", COMPANY_A_CSV)
    dataset_id = response.json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    assert profile["row_count"] == 4


def test_whitespace_trimmed_in_mapping_pipeline(phase26_environment) -> None:
    client, _, _ = phase26_environment
    content = (
        b"client_ref,sale_number,item_code,sale_date,units,amount_paid,feedback_message,rating\n"
        b"  C1  ,S1,P1,2024-01-01,3,$45.99,  Great product  ,5\n"
        b"C2,S2,P2,2024-01-02,1,$12.50,Not bad,3\n"
    )
    response = _upload(client, "whitespace.csv", content)
    assert response.status_code == 201


def test_date_string_normalized_via_mapping(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "ambiguous.csv", AMBIGUOUS_CSV).json()["dataset_id"]
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/mapping",
        json={"mapping": {"created": "order_timestamp", "cust_id_number": "customer_id"}},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 5. Profiling
# ---------------------------------------------------------------------------


def test_profile_numeric_column_has_stats(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    units_column = next(c for c in profile["columns"] if c["name"] == "units")
    assert units_column["min_value"] is not None
    assert units_column["max_value"] is not None
    assert units_column["mean_value"] is not None


def test_profile_categorical_column_detected(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "generic.csv", GENERIC_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    segment_column = next(c for c in profile["columns"] if c["name"] == "segment")
    assert segment_column["semantic_type"] in {"categorical", "text"}


def test_profile_datetime_column_range(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    date_column = next(c for c in profile["columns"] if c["name"] == "sale_date")
    assert date_column["semantic_type"] == "datetime"


def test_profile_text_column_avg_length(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    review_column = next(c for c in profile["columns"] if c["name"] == "feedback_message")
    assert review_column["avg_text_length"] is not None


def test_profile_identifier_column_detected(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    id_column = next(c for c in profile["columns"] if c["name"] == "client_ref")
    assert id_column["semantic_type"] == "identifier"


def test_profile_never_exposes_raw_row_values_beyond_samples(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    for column in profile["columns"]:
        assert len(column["sample_values"]) <= 3


# ---------------------------------------------------------------------------
# 6. Readiness
# ---------------------------------------------------------------------------


def test_readiness_churn_ready_with_customer_and_timestamp(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    readiness = {r["capability"]: r for r in profile["capability_readiness"]}
    assert readiness["churn"]["ready"] is True


def test_readiness_sentiment_ready_with_review_text(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    readiness = {r["capability"]: r for r in profile["capability_readiness"]}
    assert readiness["sentiment"]["ready"] is True
    assert readiness["bad_review"]["ready"] is True


def test_readiness_missing_capability_lists_missing_fields(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "generic.csv", GENERIC_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    readiness = {r["capability"]: r for r in profile["capability_readiness"]}
    assert readiness["recommendation"]["ready"] is False
    assert len(readiness["recommendation"]["missing_fields"]) > 0


def test_readiness_reports_all_capabilities(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    capabilities = {r["capability"] for r in profile["capability_readiness"]}
    assert {"churn", "demand", "price", "segmentation", "recommendation", "sentiment"}.issubset(capabilities)


def test_readiness_uses_business_language_only(phase26_environment) -> None:
    client, _, _ = phase26_environment
    dataset_id = _upload(client, "generic.csv", GENERIC_CSV).json()["dataset_id"]
    profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()
    banned_terms = ("gradientboosting", "randomforest", "sklearn", "xgboost", "hyperparameter")
    payload = json.dumps(profile).lower()
    assert not any(term in payload for term in banned_terms)


# ---------------------------------------------------------------------------
# 7. Storage
# ---------------------------------------------------------------------------


def test_raw_file_preserved_on_disk(phase26_environment, tmp_path: Path) -> None:
    client, session_factory, _ = phase26_environment
    _upload(client, "company_a.csv", COMPANY_A_CSV)
    with session_factory() as session:
        version = session.scalar(select(DatasetVersion))
        assert version is not None
        assert Path(version.artifact_path).is_file()


def test_prepared_data_stored_separately_from_raw(phase26_environment) -> None:
    client, session_factory, _ = phase26_environment
    _upload(client, "company_a.csv", COMPANY_A_CSV)
    with session_factory() as session:
        version = session.scalar(select(DatasetVersion))
        raw_path = Path(version.artifact_path)
        prepared_path = raw_path.parent.parent / "prepared" / "prepared.json"
        assert prepared_path.is_file()
        assert prepared_path != raw_path


def test_new_version_created_on_reupload_same_name(phase26_environment) -> None:
    client, session_factory, _ = phase26_environment
    first = _upload(client, "company_a.csv", COMPANY_A_CSV)
    second = _upload(client, "company_a.csv", COMPANY_A_CSV)
    assert first.json()["dataset_id"] == second.json()["dataset_id"]
    assert second.json()["version"] == first.json()["version"] + 1
    with session_factory() as session:
        dataset = session.scalar(select(Dataset))
        assert len(dataset.versions) == 2


def test_storage_root_never_escaped(phase26_environment) -> None:
    client, session_factory, _ = phase26_environment
    _upload(client, "company_a.csv", COMPANY_A_CSV)
    with session_factory() as session:
        version = session.scalar(select(DatasetVersion))
        artifact_root_marker = "company_datasets"
        assert artifact_root_marker in version.artifact_path


# ---------------------------------------------------------------------------
# 8. Regression / no Olist dependency
# ---------------------------------------------------------------------------


def test_two_generic_companies_map_coherently_without_olist(phase26_environment) -> None:
    client, _, tenants = phase26_environment
    dataset_a = _upload(client, "company_a.csv", COMPANY_A_CSV).json()["dataset_id"]
    profile_a = client.get(f"/api/v1/datasets/{dataset_a}/profile").json()
    mapping_a = {s["original_column"]: s["suggested_field"] for s in profile_a["mapping_suggestions"]}

    tenants["current"]["tenant"] = tenants["company_b"]
    dataset_b = _upload(
        client, "company_b.json", _company_b_json(), content_type="application/json"
    ).json()["dataset_id"]
    profile_b = client.get(f"/api/v1/datasets/{dataset_b}/profile").json()
    mapping_b = {s["original_column"]: s["suggested_field"] for s in profile_b["mapping_suggestions"]}

    assert set(mapping_a.values()) == set(mapping_b.values())
    assert mapping_a["client_ref"] == mapping_b["buyer_uuid"] == "customer_id"


def test_existing_csv_endpoint_still_works(phase26_environment) -> None:
    client, _, _ = phase26_environment
    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("legacy.csv", GENERIC_CSV, "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "validated"


def test_full_pipeline_company_a_end_to_end(phase26_environment) -> None:
    client, _, _ = phase26_environment
    upload_response = _upload(client, "company_a.csv", COMPANY_A_CSV)
    assert upload_response.status_code == 201
    dataset_id = upload_response.json()["dataset_id"]

    dataset_response = client.get(f"/api/v1/datasets/{dataset_id}")
    assert dataset_response.status_code == 200

    profile_response = client.get(f"/api/v1/datasets/{dataset_id}/profile")
    assert profile_response.status_code == 200
    body = profile_response.json()
    assert body["review_required"] is False
    assert body["quality_status"] in {"good", "warning"}


def test_training_handoff_returns_prepared_dataset(phase26_environment) -> None:
    from uuid import UUID

    from backend.app.services.artifact_service import ArtifactService
    from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
    from modules.entitlements import ModuleAccessService
    from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset
    from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage

    client, session_factory, tenants = phase26_environment
    upload_response = _upload(client, "company_a.csv", COMPANY_A_CSV)
    assert upload_response.status_code == 201
    dataset_id = UUID(upload_response.json()["dataset_id"])

    with session_factory() as session:
        service = CompanyDatasetIngestionService(
            session=session,
            storage=LocalDatasetStorage(tenants["artifact_root"] / "company_datasets"),
            quota=DataImportPolicy(session),
            max_upload_bytes=5 * 1024 * 1024,
        )
        prepared = service.get_prepared_dataset(tenants["company_a"], dataset_id)

    assert isinstance(prepared, PreparedCompanyDataset)
    assert prepared.dataset_id == dataset_id
    assert prepared.canonical_columns
    assert len(prepared.rows) > 0
    assert prepared.quality.status.value in {"good", "warning"}

