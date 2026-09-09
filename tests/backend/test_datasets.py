from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.datasets import get_dataset_import_service
from backend.app.models import (
    Base,
    AuthSession,
    AuditLogEntry,
    BillingAccount,
    CommerceConnection,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    Dataset,
    DatasetVersion,
    DatasetVersionStatus,
    ModelRegistry,
    Module,
    NormalizedCommerceRecord,
    RetailActiveSource,
    TrainingJob,
    User,
)
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.dataset_import_service import DatasetImportService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from shared.ai_engine.contracts import TenantContext

CSV_CONTENT = b"id,age,segment\n1,20,A\n2,,B\n2,,B\n"


@pytest.fixture
def dataset_environment(
    tmp_path: Path,
) -> Generator[tuple[TestClient, sessionmaker[Session], dict[str, TenantContext], Path], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'datasets.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as session:
        companies = [
            Company(
                name=name,
                slug=slug,
                email=email,
                country="Canada",
                timezone="America/Toronto",
                industry="Retail",
                subscription_plan="professional",
            )
            for name, slug, email in (
                ("Acme", "acme", "acme@example.ca"),
                ("Nova", "nova", "nova@example.ca"),
                ("No Access", "no-access", "no-access@example.ca"),
            )
        ]
        module = Module(name="RetailSenseAI", code="retail", is_active=True)
        session.add_all([*companies, module])
        session.flush()
        now = datetime.now(timezone.utc)
        session.add_all([
            CompanyModule(
                company_id=company.id,
                module_id=module.id,
                activated_at=now - timedelta(minutes=1),
                status=CompanyModuleStatus.ACTIVE,
            )
            for company in companies[:2]
        ])
        session.add_all([
            BillingAccount(
                company_id=company.id,
                plan_code=company.subscription_plan,
                status="active",
            )
            for company in companies
        ])
        user = User(
            company_id=companies[0].id,
            first_name="Data",
            last_name="Owner",
            email="data-owner@example.ca",
            password_hash="test-hash",
            is_platform_admin=False,
        )
        session.add(user)
        session.flush()
        auth_session = AuthSession(
            user_id=user.id,
            token_hash="dataset-tests-token",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        session.add(auth_session)
        session.commit()
        identity = CurrentIdentity(auth_session, user, "test-token")
        tenants = {
            "acme": TenantContext(companies[0].id),
            "nova": TenantContext(companies[1].id),
            "no_access": TenantContext(companies[2].id),
        }

    current = {"tenant": tenants["acme"]}
    artifact_root = tmp_path / "artifacts"
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_dataset_service() -> Generator[DatasetImportService, None, None]:
        with session_factory() as session:
            yield DatasetImportService(
                session=session,
                artifacts=ArtifactService(artifact_root),
                quota=DataImportPolicy(session),
                max_upload_bytes=1024 * 1024,
                audit_log=AuditLogService(session),
            )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: current["tenant"]
    app.dependency_overrides[get_current_identity] = lambda: identity
    app.dependency_overrides[get_dataset_import_service] = override_dataset_service
    with TestClient(app) as client:
        yield client, session_factory, {**tenants, "current": current}, artifact_root


def test_csv_import_creates_tenant_profile_and_artifact(dataset_environment) -> None:
    client, session_factory, tenants, artifact_root = dataset_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", CSV_CONTENT, "text/csv")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "validated"
    assert body["rows_count"] == 3
    assert body["columns_count"] == 3
    assert body["numerical_columns"] == 2
    assert body["categorical_columns"] == 1
    assert body["missing_values"] == 2
    assert body["duplicates"] == 1
    assert [column["inferred_type"] for column in body["columns"]] == [
        "integer",
        "integer",
        "string",
    ]
    with session_factory() as session:
        dataset = session.scalar(select(Dataset))
        assert dataset is not None
        source = Path(dataset.source)
        assert str(tenants["acme"].company_id) in source.parts
        assert source.is_file()
        assert artifact_root.resolve() in source.parents
        assert session.scalars(select(TrainingJob)).all() == []
        assert session.scalars(select(ModelRegistry)).all() == []
        assert list(artifact_root.rglob("*"))[-1] == source


def test_dataset_routes_hide_other_tenants(dataset_environment) -> None:
    client, _, tenants, _ = dataset_environment
    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", CSV_CONTENT, "text/csv")},
    )
    dataset_id = upload.json()["id"]

    tenants["current"]["tenant"] = tenants["nova"]

    assert client.get("/api/v1/datasets").json() == []
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404


def test_dataset_routes_block_inactive_subscription(dataset_environment) -> None:
    client, session_factory, tenants, _ = dataset_environment
    with session_factory() as session:
        account = session.scalar(
            select(BillingAccount).where(
                BillingAccount.company_id == tenants["acme"].company_id,
            )
        )
        assert account is not None
        account.status = "inactive"
        session.commit()

    response = client.get("/api/v1/datasets")

    assert response.status_code == 402
    assert response.json()["error"]["message"] == "Un abonnement actif est requis"


def test_dataset_lookup_and_delete_convert_path_id_to_uuid(
    dataset_environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _, _ = dataset_environment
    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", CSV_CONTENT, "text/csv")},
    )
    dataset_id = upload.json()["id"]
    received_ids: list[UUID] = []
    original_get = DatasetImportService.get
    original_delete = DatasetImportService.delete

    def recording_get(self, tenant, received_id):
        received_ids.append(received_id)
        return original_get(self, tenant, received_id)

    def recording_delete(self, tenant, received_id, **kwargs):
        received_ids.append(received_id)
        return original_delete(self, tenant, received_id, **kwargs)

    monkeypatch.setattr(DatasetImportService, "get", recording_get)
    monkeypatch.setattr(DatasetImportService, "delete", recording_delete)

    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 200
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 204
    assert received_ids
    assert all(isinstance(received_id, UUID) for received_id in received_ids)


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_dataset_routes_reject_invalid_uuid_before_service_call(
    method: str,
    dataset_environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _, _ = dataset_environment

    def unexpected_call(*args, **kwargs):
        raise AssertionError("Le service ne doit pas recevoir un UUID invalide")

    monkeypatch.setattr(DatasetImportService, "get", unexpected_call)
    monkeypatch.setattr(DatasetImportService, "delete", unexpected_call)

    response = client.request(method, "/api/v1/datasets/not-a-uuid")

    assert response.status_code == 422


def test_dataset_delete_is_tenant_scoped_and_removes_artifacts(dataset_environment) -> None:
    client, session_factory, tenants, _ = dataset_environment
    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", CSV_CONTENT, "text/csv")},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    with session_factory() as session:
        dataset = session.get(Dataset, UUID(dataset_id))
        assert dataset is not None
        source = Path(dataset.source)
        dataset_root = source.parent
        assert source.is_file()
        assert dataset_root.is_dir()

    # Une autre entreprise ne peut ni voir ni supprimer le fichier.
    tenants["current"]["tenant"] = tenants["nova"]
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 403
    assert source.is_file()

    # Le propriétaire peut supprimer le dataset, ses métadonnées et son dossier.
    tenants["current"]["tenant"] = tenants["acme"]
    response = client.delete(f"/api/v1/datasets/{dataset_id}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404
    assert client.get("/api/v1/datasets").json() == []
    assert not dataset_root.exists()


def test_delete_many_removes_synchronized_data_but_preserves_connection(
    dataset_environment,
) -> None:
    _, session_factory, tenants, artifact_root = dataset_environment
    acme = tenants["acme"]
    nova = tenants["nova"]

    with session_factory() as session:
        service = DatasetImportService(
            session=session,
            artifacts=ArtifactService(artifact_root),
            quota=DataImportPolicy(session),
            max_upload_bytes=1024 * 1024,
            audit_log=AuditLogService(session),
        )
        selected = service.import_csv(acme, "retail", "shopify.csv", CSV_CONTENT)
        retained = service.import_csv(nova, "retail", "nova.csv", CSV_CONTENT)
        connection = CommerceConnection(
            company_id=acme.company_id,
            provider="shopify",
            external_account_id="shop.example",
            status="CONNECTED",
            encrypted_credentials="encrypted-value",
            dataset_ids={"retail": str(selected.id)},
            sync_cursor={"orders": "cursor"},
            records_processed=1,
        )
        session.add(connection)
        session.flush()
        session.add_all(
            [
                NormalizedCommerceRecord(
                    company_id=acme.company_id,
                    connection_id=connection.id,
                    provider="shopify",
                    entity_type="orders",
                    source_record_id="order-1",
                    normalized_data={"id": "order-1"},
                ),
                RetailActiveSource(
                    company_id=acme.company_id,
                    source_type="connection",
                    dataset_id=selected.id,
                    connection_id=connection.id,
                ),
            ]
        )
        session.commit()
        connection_id = connection.id
        selected_id = selected.id
        retained_id = retained.id

        actor_id = session.scalar(
            select(User.id).where(User.company_id == acme.company_id)
        )
        assert actor_id is not None
        service.delete_many(acme, [selected_id], actor_user_id=actor_id)

        preserved = session.get(CommerceConnection, connection_id)
        assert preserved is not None
        assert preserved.status == "CONNECTED"
        assert preserved.encrypted_credentials == "encrypted-value"
        assert preserved.dataset_ids == {}
        assert preserved.sync_cursor == {}
        assert session.get(Dataset, selected_id) is None
        assert session.get(Dataset, retained_id) is not None
        assert session.scalar(
            select(NormalizedCommerceRecord).where(
                NormalizedCommerceRecord.connection_id == connection_id
            )
        ) is None
        assert session.scalar(
            select(RetailActiveSource).where(
                RetailActiveSource.company_id == acme.company_id
            )
        ) is None
        audit = session.scalar(
            select(AuditLogEntry).where(AuditLogEntry.target_id == str(selected_id))
        )
        assert audit is not None
        assert audit.safe_metadata == {
            "result": "success",
            "source_type": "synchronized",
            "connectors": [
                {"connection_id": str(connection_id), "provider": "shopify"}
            ],
        }


def test_delete_selection_is_atomic_tenant_scoped_and_audited(
    dataset_environment,
) -> None:
    client, session_factory, tenants, artifact_root = dataset_environment
    own_ids = []
    for filename in ("sales.csv", "customers.csv"):
        response = client.post(
            "/api/v1/datasets/csv",
            data={"module_code": "retail"},
            files={"file": (filename, CSV_CONTENT, "text/csv")},
        )
        assert response.status_code == 201
        own_ids.append(response.json()["id"])

    with session_factory() as session:
        service = DatasetImportService(
            session=session,
            artifacts=ArtifactService(artifact_root),
            quota=DataImportPolicy(session),
            max_upload_bytes=1024 * 1024,
        )
        foreign = service.import_csv(
            tenants["nova"],
            "retail",
            "foreign.csv",
            CSV_CONTENT,
        )
        foreign_id = str(foreign.id)

    forbidden = client.post(
        "/api/v1/datasets/delete-selection",
        json={"dataset_ids": [own_ids[0], foreign_id]},
    )
    assert forbidden.status_code == 403
    assert client.get(f"/api/v1/datasets/{own_ids[0]}").status_code == 200

    missing = client.post(
        "/api/v1/datasets/delete-selection",
        json={"dataset_ids": ["77777777-7777-7777-7777-777777777777"]},
    )
    assert missing.status_code == 404

    deleted = client.post(
        "/api/v1/datasets/delete-selection",
        json={"dataset_ids": own_ids},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_count"] == 2
    assert set(deleted.json()["deleted_ids"]) == set(own_ids)

    with session_factory() as session:
        assert session.get(Dataset, UUID(foreign_id)) is not None
        entries = list(
            session.scalars(
                select(AuditLogEntry).where(
                    AuditLogEntry.action == "dataset_deleted",
                    AuditLogEntry.company_id == tenants["acme"].company_id,
                )
            )
        )
        assert {entry.target_id for entry in entries} == set(own_ids)
        assert all(entry.safe_metadata["result"] == "success" for entry in entries)


def test_csv_import_succeeds_without_active_module_core_capability(dataset_environment) -> None:
    """L'ingestion de données est une capacité CORE Avenqo : une entreprise
    sans module optionnel actif peut tout de même importer un CSV."""
    client, _, tenants, _ = dataset_environment
    tenants["current"]["tenant"] = tenants["no_access"]

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", CSV_CONTENT, "text/csv")},
    )

    assert response.status_code == 201
