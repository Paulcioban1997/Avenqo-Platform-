import pytest

from tests.security.isolated_postgres import require_isolated_admin_url


def test_missing_url_skips(monkeypatch) -> None:
    monkeypatch.delenv("AVENQO_ROTATION_TEST_ADMIN_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    with pytest.raises(pytest.skip.Exception):
        require_isolated_admin_url()


def test_stopped_server_skips_instead_of_failing(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv(
        "AVENQO_ROTATION_TEST_ADMIN_URL",
        "postgresql+psycopg2://postgres:test-only-password@127.0.0.1:54329/rotation_test_ci",
    )
    with pytest.raises(pytest.skip.Exception, match="not reachable"):
        require_isolated_admin_url()


def test_non_localhost_url_fails(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv(
        "AVENQO_ROTATION_TEST_ADMIN_URL",
        "postgresql+psycopg2://postgres:test-only-password@db.example.internal:5432/rotation_test_ci",
    )
    with pytest.raises(pytest.fail.Exception, match="localhost"):
        require_isolated_admin_url()
