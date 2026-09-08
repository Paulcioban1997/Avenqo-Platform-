from fastapi.testclient import TestClient

from backend.app.services.artifact_storage_health import (
    ArtifactStorageStatus,
    artifact_storage_health,
)
from backend.main import app

client = TestClient(app)


def test_root_returns_200() -> None:
    response = client.get("/")
    assert response.status_code == 200


def test_health_returns_200() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_readiness_is_degraded_when_artifact_storage_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        artifact_storage_health,
        "check",
        lambda root: ArtifactStorageStatus(
            status="unavailable",
            readable=True,
            writable=False,
            nested_directories=False,
        ),
    )

    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["artifact_storage"] == "unavailable"


def test_health_response_contains_request_id_header() -> None:
    response = client.get("/api/v1/health")
    assert "X-Request-ID" in response.headers


def test_client_provided_request_id_is_preserved() -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_unknown_route_returns_json_error() -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["success"] is False
