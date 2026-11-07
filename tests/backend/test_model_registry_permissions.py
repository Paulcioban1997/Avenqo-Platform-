"""Tests de non-régression P0 pour le registre de modèles, la navigation et l'étanchéité aux erreurs filesystem."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.app.config.settings import get_settings
from backend.app.dependencies.ai_engine import get_model_registry_root, _is_usable_directory
from backend.app.dependencies.auth import get_tenant_context, get_current_identity, CurrentIdentity
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.models.auth_session import AuthSession
from backend.app.models.base import UserRole, CompanyStatus
from backend.app.models.company import Company
from backend.app.models.user import User
from shared.ai_engine.contracts import TenantContext


def test_model_registry_root_normal_creation(tmp_path, monkeypatch):
    test_dir = tmp_path / "models_test"
    monkeypatch.setattr(get_settings(), "model_registry_root", str(test_dir))
    root = get_model_registry_root()
    assert root.exists()
    assert root.is_dir()
    assert root == test_dir


def test_model_registry_root_multi_tier_fallback_on_permission_denied(monkeypatch, tmp_path):
    """Vérifie que lors d'un PermissionError (Errno 13) sur la destination principale,
    le système bascule de façon étanche vers un candidat persistant ou temporaire garanti existant et accessible."""
    settings = get_settings()
    monkeypatch.setattr(settings, "model_registry_root", "/srv/var/models")
    
    # Configure an accessible persistent directory under tmp_path
    persistent_dir = tmp_path / "artifacts"
    persistent_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "artifact_root", str(persistent_dir))

    # Mock Path.mkdir so that /srv/var/models fails with PermissionError
    orig_mkdir = Path.mkdir

    def selective_mkdir(self, *args, **kwargs):
        path_str = str(self).replace("\\", "/")
        if "/srv/var/models" in path_str:
            raise PermissionError(13, f"Permission denied: '{self}'")
        return orig_mkdir(self, *args, **kwargs)

    with patch.object(Path, "mkdir", selective_mkdir):
        root = get_model_registry_root()
        assert root is not None
        assert root.exists()
        assert root.is_dir()
        assert str(root) != "/srv/var/models"
        # Must be usable for write operations
        assert _is_usable_directory(root) is True


def test_model_registry_never_returns_inaccessible_or_nonexistent_path(monkeypatch):
    """Garantit formellement que get_model_registry_root ne retourne JAMAIS un chemin inexistant ou inaccessible."""
    settings = get_settings()
    monkeypatch.setattr(settings, "model_registry_root", "/root/forbidden/models")

    root = get_model_registry_root()
    assert root.exists(), f"Returned root path {root} must exist on disk"
    assert root.is_dir(), f"Returned root path {root} must be a directory"
    
    # Verify that unprivileged write succeeds
    probe = root / f".test_probe_{uuid4().hex[:6]}"
    probe.write_text("verification_ok", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "verification_ok"
    probe.unlink(missing_ok=True)


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import get_db
from backend.app.database.session import Base


def test_all_ten_failing_endpoints_resilient_to_filesystem_error(tmp_path):
    """Vérifie que les 10 routes ayant échoué en 500 lors de l'incident P0 ne retournent
    PLUS JAMAIS HTTP 500 lorsque le chemin primaire du registre de modèles est bloqué par permissions."""
    db_path = tmp_path / "test_resilience.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    cid = uuid4()
    uid = uuid4()
    mock_company = Company(
        id=cid,
        name="Produits_Ero Pilot",
        slug="produits-ero-pilot",
        email="contact@produits-ero.ca",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="base",
        status=CompanyStatus.ACTIVE,
    )
    mock_user = User(
        id=uid,
        company_id=cid,
        first_name="Pilot",
        last_name="Owner",
        password_hash="fake_hash",
        email="owner@produits-ero.ca",
        role=UserRole.OWNER,
        is_platform_admin=False,
    )
    mock_session = AuthSession(id=uuid4(), user_id=uid)

    with session_factory() as session:
        session.add(mock_company)
        session.add(mock_user)
        session.commit()

    mock_user.company = mock_company
    mock_identity = CurrentIdentity(
        auth_session=mock_session,
        user=mock_user,
        raw_token="jwt_token_test",
    )

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(cid)
    app.dependency_overrides[get_current_identity] = lambda: mock_identity
    app.dependency_overrides[require_active_subscription] = lambda: mock_company

    orig_mkdir = Path.mkdir

    def selective_mkdir(self, *args, **kwargs):
        path_str = str(self).replace("\\", "/")
        if "/srv/var/models" in path_str:
            raise PermissionError(13, f"Permission denied: '{self}'")
        return orig_mkdir(self, *args, **kwargs)

    failing_endpoints = [
        "/api/v1/dashboard",
        "/api/v1/retail/products",
        "/api/v1/retail/orders",
        "/api/v1/retail/inventory",
        "/api/v1/sales/summary",
        "/api/v1/voice/status",
        "/api/v1/agents",
        "/api/v1/datasets",
        "/api/v1/contracts",
        "/api/v1/ai/chat/conversations",
    ]

    try:
        with patch.object(Path, "mkdir", selective_mkdir):
            client = TestClient(app, base_url="https://api.avenqo.ca", raise_server_exceptions=False)
            headers = {"Host": "api.avenqo.ca"}

            for endpoint in failing_endpoints:
                res = client.get(endpoint, headers=headers)
                assert res.status_code != 500, (
                    f"CRITICAL: Endpoint '{endpoint}' returned HTTP 500: {res.text}"
                )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_tenant_context, None)
        app.dependency_overrides.pop(get_current_identity, None)
        app.dependency_overrides.pop(require_active_subscription, None)
