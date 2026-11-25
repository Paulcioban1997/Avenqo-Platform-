"""Comprehensive test suite for PR 4 multi-format dataset exports, security, and RBAC."""

from __future__ import annotations

from collections.abc import Generator
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO, StringIO
import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from openpyxl import load_workbook
import pyarrow.parquet as pq
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.datasets import (
    get_company_dataset_ingestion_service,
    get_dataset_import_service,
)
from backend.app.models import (
    AuthSession,
    Base,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    Dataset,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
    Module,
    User,
    UserRole,
)
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.app.services.dataset_export_service import (
    DatasetExportService,
    is_genuine_signed_number_str,
    sanitize_spreadsheet_cell,
)
from backend.app.services.dataset_import_service import DatasetImportService
from backend.main import create_application
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage
from tests.subscription_helpers import add_active_subscription


ACCENTED_FORMULA_CSV = (
    "client_ref,nom_client,ville,montant_facture,solde_signe,note_audit\n"
    "C-001,Éléonore Gagnon,Montréal,1245.55,-45.99,=CMD|' /C calc'!A0\n"
    "C-002,François Bélanger,Québec,890.10,+12.50,+SUM(A1:A2)\n"
    "C-003,Chloé Côté,Trois-Rivières,,0.00,@IMPORTXML(A1)\n"
).encode("utf-8")


@pytest.fixture
def export_env(
    tmp_path: Path,
) -> Generator[tuple[TestClient, sessionmaker[Session], dict, Path], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pr4_exports.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    now = datetime.now(timezone.utc)
    with session_factory() as session:
        company_a = Company(
            name="Entreprise Alpha",
            slug="entreprise-alpha",
            email="alpha@example.ca",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        company_b = Company(
            name="Entreprise Beta",
            slug="entreprise-beta",
            email="beta@example.ca",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        retail_mod = Module(name="RetailSenseAI", code="retail", is_active=True)
        session.add_all([company_a, company_b, retail_mod])
        session.flush()

        for comp in (company_a, company_b):
            session.add(
                CompanyModule(
                    company_id=comp.id,
                    module_id=retail_mod.id,
                    activated_at=now - timedelta(minutes=5),
                    status=CompanyModuleStatus.ACTIVE,
                )
            )
            add_active_subscription(session, comp)

        owner_user = User(
            company_id=company_a.id,
            first_name="Claire",
            last_name="Dirigeante",
            email="owner-alpha@example.ca",
            password_hash="hash",
            role=UserRole.OWNER,
            is_platform_admin=False,
        )
        viewer_user = User(
            company_id=company_a.id,
            first_name="Luc",
            last_name="Lecteur",
            email="viewer-alpha@example.ca",
            password_hash="hash",
            role=UserRole.VIEWER,
            is_platform_admin=False,
        )
        company_b_owner = User(
            company_id=company_b.id,
            first_name="Marc",
            last_name="Beta",
            email="owner-beta@example.ca",
            password_hash="hash",
            role=UserRole.OWNER,
            is_platform_admin=False,
        )
        session.add_all([owner_user, viewer_user, company_b_owner])
        session.flush()

        owner_sess = AuthSession(
            user_id=owner_user.id,
            token_hash="tok-owner-a",
            created_at=now,
            expires_at=now + timedelta(hours=2),
        )
        viewer_sess = AuthSession(
            user_id=viewer_user.id,
            token_hash="tok-viewer-a",
            created_at=now,
            expires_at=now + timedelta(hours=2),
        )
        b_sess = AuthSession(
            user_id=company_b_owner.id,
            token_hash="tok-owner-b",
            created_at=now,
            expires_at=now + timedelta(hours=2),
        )
        session.add_all([owner_sess, viewer_sess, b_sess])
        session.commit()

        identities = {
            "owner_a": CurrentIdentity(owner_sess, owner_user, "tok-owner-a"),
            "viewer_a": CurrentIdentity(viewer_sess, viewer_user, "tok-viewer-a"),
            "owner_b": CurrentIdentity(b_sess, company_b_owner, "tok-owner-b"),
        }
        tenants = {
            "company_a": TenantContext(company_a.id, user_id=owner_user.id),
            "company_b": TenantContext(company_b.id, user_id=company_b_owner.id),
        }

    state = {
        "tenant": tenants["company_a"],
        "identity": identities["owner_a"],
    }
    artifact_root = tmp_path / "artifacts"
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_ingestion() -> Generator[CompanyDatasetIngestionService, None, None]:
        with session_factory() as session:
            yield CompanyDatasetIngestionService(
                session=session,
                storage=LocalDatasetStorage(artifact_root / "company_datasets"),
                quota=DataImportPolicy(session, artifact_root),
                max_upload_bytes=10 * 1024 * 1024,
            )

    def override_import() -> Generator[DatasetImportService, None, None]:
        with session_factory() as session:
            yield DatasetImportService(
                session=session,
                artifacts=ArtifactService(artifact_root),
                quota=DataImportPolicy(session, artifact_root),
                max_upload_bytes=10 * 1024 * 1024,
                audit_log=AuditLogService(session),
            )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: state["tenant"]
    app.dependency_overrides[get_current_identity] = lambda: state["identity"]
    app.dependency_overrides[get_company_dataset_ingestion_service] = override_ingestion
    app.dependency_overrides[get_dataset_import_service] = override_import

    with TestClient(app) as client:
        yield client, session_factory, {"state": state, "tenants": tenants, "identities": identities}, artifact_root


def _upload_csv_dataset(client: TestClient, filename: str, payload: bytes) -> str:
    resp = client.post(
        "/api/v1/datasets/upload",
        data={"module_code": "retail"},
        files={"file": (filename, payload, "text/csv")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["dataset_id"]


def test_all_eight_export_formats_content_accents_nulls_and_headers(export_env) -> None:
    """Verify CSV, XLSX, JSON, Parquet, PDF, DOCX, TXT, and original exports work end-to-end."""
    client, _, _, artifact_root = export_env
    dataset_id = _upload_csv_dataset(client, "ventes_québec.csv", ACCENTED_FORMULA_CSV)

    # 1. CSV: UTF-8 accents, exact column order, nulls empty, formula neutralized, signed numbers intact
    csv_resp = client.get(f"/api/v1/datasets/{dataset_id}/export/csv")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["X-Export-Row-Count"] == "3"
    assert csv_resp.headers["X-Export-Scope"] == "cleaned"
    assert csv_resp.headers["X-Export-Paginated"] == "false"
    parsed_csv = list(csv.reader(StringIO(csv_resp.content.decode("utf-8"))))
    assert parsed_csv[0] == [
        "client_ref",
        "nom_client",
        "ville",
        "montant_facture",
        "solde_signe",
        "note_audit",
    ]
    assert len(parsed_csv) == 4
    assert parsed_csv[1][1] == "Éléonore Gagnon"
    assert parsed_csv[1][2] == "Montréal"
    assert parsed_csv[1][4] in ("-45.99", "-45.9900")
    # Formula injection neutralized with leading single quote
    assert parsed_csv[1][5].startswith("'=CMD|")
    assert parsed_csv[2][5].startswith("'+SUM(")
    assert parsed_csv[3][5].startswith("'@IMPORTXML")
    # Null value serialized cleanly as empty string
    assert parsed_csv[3][3] == ""

    # 2. XLSX: typed cells, header styling, formula injection neutralized, exact row count
    xlsx_resp = client.get(f"/api/v1/datasets/{dataset_id}/export/xlsx")
    assert xlsx_resp.status_code == 200
    wb = load_workbook(BytesIO(xlsx_resp.content))
    ws = wb.active
    assert ws is not None
    assert ws.max_row == 4
    assert [c.value for c in ws[1]] == [
        "client_ref",
        "nom_client",
        "ville",
        "montant_facture",
        "solde_signe",
        "note_audit",
    ]
    assert ws.cell(row=1, column=1).font.bold is True
    assert ws.cell(row=2, column=2).value == "Éléonore Gagnon"
    assert str(ws.cell(row=2, column=6).value).startswith("'=CMD|")
    assert ws.cell(row=4, column=4).value in (None, "")

    # 3. JSON: structured UTF-8 envelope + raw records mode, never leaking filesystem paths
    json_env_resp = client.get(f"/api/v1/datasets/{dataset_id}/export/json?envelope=true")
    assert json_env_resp.status_code == 200
    env_body = json.loads(json_env_resp.content.decode("utf-8"))
    assert env_body["metadata"]["dataset_id"] == dataset_id
    assert env_body["metadata"]["row_count"] == 3
    assert env_body["metadata"]["scope"] == "cleaned"
    assert str(artifact_root) not in json_env_resp.text
    assert env_body["records"][0]["nom_client"] == "Éléonore Gagnon"

    json_raw_resp = client.get(f"/api/v1/datasets/{dataset_id}/export/json?envelope=false")
    assert json_raw_resp.status_code == 200
    raw_records = json.loads(json_raw_resp.content.decode("utf-8"))
    assert isinstance(raw_records, list) and len(raw_records) == 3

    # 4. Parquet: readable via pyarrow with UTF-8 accents, nulls, and exact column order
    pq_resp = client.get(f"/api/v1/datasets/{dataset_id}/export/parquet")
    assert pq_resp.status_code == 200
    arrow_table = pq.read_table(BytesIO(pq_resp.content))
    assert arrow_table.num_rows == 3
    assert arrow_table.column_names == [
        "client_ref",
        "nom_client",
        "ville",
        "montant_facture",
        "solde_signe",
        "note_audit",
    ]
    assert arrow_table.column("nom_client").to_pylist() == [
        "Éléonore Gagnon",
        "François Bélanger",
        "Chloé Côté",
    ]

    # 5. PDF: clear distinction between Tabular Data PDF vs Quality Report PDF
    pdf_tabular = client.get(f"/api/v1/datasets/{dataset_id}/export/pdf?scope=cleaned")
    assert pdf_tabular.status_code == 200
    assert pdf_tabular.content.startswith(b"%PDF")
    assert "tabular.pdf" in pdf_tabular.headers["Content-Disposition"]
    assert pdf_tabular.headers["X-Export-Scope"] == "cleaned"

    pdf_report = client.get(f"/api/v1/datasets/{dataset_id}/export/pdf?scope=quality_report")
    assert pdf_report.status_code == 200
    assert pdf_report.content.startswith(b"%PDF")
    assert "quality-report.pdf" in pdf_report.headers["Content-Disposition"]
    assert pdf_report.headers["X-Export-Scope"] == "quality_report"
    assert pdf_tabular.content != pdf_report.content

    # 6. DOCX: clear distinction between Tabular DOCX vs Quality Report DOCX
    docx_tabular = client.get(f"/api/v1/datasets/{dataset_id}/export/docx?scope=cleaned")
    assert docx_tabular.status_code == 200
    assert "tabular.docx" in docx_tabular.headers["Content-Disposition"]
    tab_doc = DocxDocument(BytesIO(docx_tabular.content))
    assert any("Export de données tabulaires" in p.text for p in tab_doc.paragraphs)
    assert len(tab_doc.tables) == 1
    assert len(tab_doc.tables[0].rows) == 4  # 1 header + 3 data rows
    assert tab_doc.tables[0].rows[1].cells[1].text == "Éléonore Gagnon"

    docx_report = client.get(f"/api/v1/datasets/{dataset_id}/export/docx?scope=quality_report")
    assert docx_report.status_code == 200
    assert "quality-report.docx" in docx_report.headers["Content-Disposition"]
    rep_doc = DocxDocument(BytesIO(docx_report.content))
    assert any("Cleaning report" in p.text for p in rep_doc.paragraphs)

    # 7. TXT: aligned UTF-8 text export
    txt_resp = client.get(f"/api/v1/datasets/{dataset_id}/export/txt")
    assert txt_resp.status_code == 200
    txt_body = txt_resp.content.decode("utf-8")
    assert "Éléonore Gagnon" in txt_body
    assert "Trois-Rivières" in txt_body
    assert "client_ref" in txt_body

    # 8. Original: exact byte-for-byte authorized raw file download without path leakage
    orig_resp = client.get(f"/api/v1/datasets/{dataset_id}/export/original")
    assert orig_resp.status_code == 200
    assert orig_resp.content == ACCENTED_FORMULA_CSV
    assert "original" in orig_resp.headers["Content-Disposition"]
    assert str(artifact_root) not in str(orig_resp.headers)


def test_decimal_financial_precision_and_formula_guard_unit() -> None:
    """Verify exact Decimal precision across CSV, XLSX, JSON, Parquet, and formula guard edge cases."""
    assert sanitize_spreadsheet_cell("=1+1") == "'=1+1"
    assert sanitize_spreadsheet_cell("  +CMD|' /C notepad'!A0") == "'  +CMD|' /C notepad'!A0"
    assert sanitize_spreadsheet_cell("\t=SUM(A1)") == "'\t=SUM(A1)"
    assert sanitize_spreadsheet_cell("\r@A1") == "'\r@A1"
    # Genuine signed numbers and Decimals remain untouched
    assert is_genuine_signed_number_str("-1245.99") is True
    assert is_genuine_signed_number_str("+0.0005") is True
    assert is_genuine_signed_number_str("-2+3") is False
    assert sanitize_spreadsheet_cell("-1245.99") == "-1245.99"
    assert sanitize_spreadsheet_cell(Decimal("-98765.4321")) == Decimal("-98765.4321")

    tenant = TenantContext(company_id=uuid4())
    ds_id = uuid4()
    dataset = Dataset(
        id=ds_id,
        company_id=tenant.company_id,
        name="grand-livre-decimal.csv",
        type="csv",
        status=DatasetStatus.READY,
        rows_count=2,
        columns_count=3,
    )
    dataset.versions.append(
        DatasetVersion(
            dataset_id=ds_id,
            version_number=1,
            name="v1",
            status=DatasetVersionStatus.READY,
            is_current=True,
            row_count=2,
            column_count=3,
        )
    )

    precise_rows = [
        {
            "compte": "4100-VENTES",
            "montant_exact": Decimal("123456.7891"),
            "haute_precision": Decimal("9999999999999999.123456"),
        },
        {
            "compte": "5200-CHARGES",
            "montant_exact": Decimal("-450.0025"),
            "haute_precision": Decimal("1000000000000000.000001"),
        },
    ]

    mock_ingestion = MagicMock()
    mock_ingestion.get.return_value = dataset
    mock_ingestion.get_cleaned_rows.return_value = tuple(precise_rows)
    exporter = DatasetExportService(mock_ingestion)

    # CSV Decimal precision
    csv_out = exporter.export(tenant, ds_id, "csv")
    assert csv_out.content is not None
    csv_text = csv_out.content.decode("utf-8")
    assert "123456.7891" in csv_text
    assert "-450.0025" in csv_text
    assert "9999999999999999.123456" in csv_text

    # JSON exact Decimal token preservation
    json_out = exporter.export(tenant, ds_id, "json", envelope=False)
    assert json_out.content is not None
    parsed_dec = json.loads(json_out.content.decode("utf-8"), parse_float=Decimal)
    assert parsed_dec[0]["montant_exact"] == Decimal("123456.7891")
    assert parsed_dec[0]["haute_precision"] == Decimal("9999999999999999.123456")
    assert parsed_dec[1]["montant_exact"] == Decimal("-450.0025")

    # XLSX Decimal precision (<=15 digits numeric + >15 digits lossless string)
    xlsx_out = exporter.export(tenant, ds_id, "xlsx")
    assert xlsx_out.content is not None
    wb = load_workbook(BytesIO(xlsx_out.content))
    ws = wb.active
    assert ws is not None
    cell_val = ws.cell(row=2, column=2).value
    assert isinstance(cell_val, (int, float, Decimal, str))
    assert abs(float(cell_val) - 123456.7891) < 1e-9
    assert ws.cell(row=2, column=3).value == "9999999999999999.123456"

    # Parquet Decimal128 precision
    pq_out = exporter.export(tenant, ds_id, "parquet")
    assert pq_out.content is not None
    pq_tbl = pq.read_table(BytesIO(pq_out.content))
    assert pq_tbl.column("montant_exact").to_pylist() == [
        Decimal("123456.7891"),
        Decimal("-450.0025"),
    ]


def test_rbac_export_options_and_cross_tenant_isolation(export_env) -> None:
    """Verify RBAC gating on export-options/original download and strict 404 cross-tenant isolation."""
    client, _, ctx, _ = export_env
    dataset_id = _upload_csv_dataset(client, "confidentiel_rh.csv", ACCENTED_FORMULA_CSV)

    # Owner has data:manage -> original scope & format permitted
    owner_opts = client.get(f"/api/v1/datasets/{dataset_id}/export-options")
    assert owner_opts.status_code == 200
    owner_body = owner_opts.json()
    assert owner_body["original_available"] is True
    assert owner_body["permissions"]["can_export_original"] is True

    # Switch to read-only VIEWER in same company (has data:read, lacks data:manage)
    ctx["state"]["identity"] = ctx["identities"]["viewer_a"]
    viewer_opts = client.get(f"/api/v1/datasets/{dataset_id}/export-options")
    assert viewer_opts.status_code == 200
    viewer_body = viewer_opts.json()
    assert viewer_body["original_available"] is False
    assert viewer_body["permissions"]["can_export_original"] is False

    # Viewer CAN export cleaned / normalized / filtered_preview, but CANNOT download raw original
    assert client.get(f"/api/v1/datasets/{dataset_id}/export/csv?scope=cleaned").status_code == 200
    assert client.get(f"/api/v1/datasets/{dataset_id}/export/json?scope=normalized").status_code == 200
    assert client.get(f"/api/v1/datasets/{dataset_id}/export/original").status_code == 403
    assert client.get(f"/api/v1/datasets/{dataset_id}/export/csv?scope=original").status_code == 403

    # Switch to Company B -> strict 404 across all export & options endpoints
    ctx["state"]["tenant"] = ctx["tenants"]["company_b"]
    ctx["state"]["identity"] = ctx["identities"]["owner_b"]
    assert client.get(f"/api/v1/datasets/{dataset_id}/export-options").status_code == 404
    for fmt in ("csv", "xlsx", "json", "parquet", "pdf", "docx", "txt", "original"):
        assert client.get(f"/api/v1/datasets/{dataset_id}/export/{fmt}").status_code == 404


def test_large_volume_streaming_pagination_and_pdf_row_cap(export_env) -> None:
    """Verify streaming CSV/TXT for 1,600+ rows, offset/limit slicing, and PDF pagination notice."""
    client, _, _, _ = export_env
    lines = ["sku,produit,quantite,prix_unitaire"]
    for idx in range(1, 1601):
        lines.append(f"SKU-{idx:04d},Article Édition #{idx},{idx % 50},{19.95 + (idx % 10):.2f}")
    large_csv_bytes = ("\n".join(lines) + "\n").encode("utf-8")

    dataset_id = _upload_csv_dataset(client, "catalogue_massif.csv", large_csv_bytes)

    # Full streaming CSV (>= 1000 rows triggers chunked StreamingResponse)
    full_csv = client.get(f"/api/v1/datasets/{dataset_id}/export/csv?scope=all_authorized")
    assert full_csv.status_code == 200
    assert full_csv.headers["X-Export-Row-Count"] == "1600"
    assert full_csv.headers["X-Export-Total-Rows"] == "1600"
    assert full_csv.headers["X-Export-Paginated"] == "false"
    exported_rows = list(csv.reader(StringIO(full_csv.content.decode("utf-8"))))
    assert len(exported_rows) == 1601

    # Paginated slice with search filter
    sliced = client.get(
        f"/api/v1/datasets/{dataset_id}/export/json?scope=filtered_preview&offset=10&limit=25&envelope=true"
    )
    assert sliced.status_code == 200
    assert sliced.headers["X-Export-Row-Count"] == "25"
    assert sliced.headers["X-Export-Paginated"] == "true"
    sliced_json = sliced.json()
    assert sliced_json["metadata"]["paginated"] is True
    assert len(sliced_json["records"]) == 25

    # Tabular PDF on 1,600 rows automatically caps at DEFAULT_MAX_PDF_ROWS (1,500) and flags X-Export-Paginated=true
    capped_pdf = client.get(f"/api/v1/datasets/{dataset_id}/export/pdf?scope=cleaned")
    assert capped_pdf.status_code == 200
    assert capped_pdf.content.startswith(b"%PDF")
    assert capped_pdf.headers["X-Export-Row-Count"] == "1500"
    assert capped_pdf.headers["X-Export-Total-Rows"] == "1600"
    assert capped_pdf.headers["X-Export-Paginated"] == "true"
