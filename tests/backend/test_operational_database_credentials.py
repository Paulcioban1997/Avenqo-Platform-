import pytest
from scripts.database_runtime import require_database_url


def test_operations_fail_without_explicit_credentials():
    with pytest.raises(RuntimeError, match="no fallback credentials"):
        require_database_url({})


def test_new_rotated_login_is_used_and_public_url_cannot_override_it():
    from sqlalchemy.engine import URL
    import secrets
    rotated = URL.create("postgresql", username="avenqo_app_v2", password=secrets.token_urlsafe(40), host="db.test.invalid", database="test").render_as_string(hide_password=False)
    assert require_database_url({"DATABASE_URL": rotated, "DATABASE_PUBLIC_URL": "sqlite:///:memory:"}) == rotated


def test_invalid_configuration_is_not_echoed():
    value = "invalid-test-configuration"
    with pytest.raises(RuntimeError) as error:
        require_database_url({"DATABASE_URL": value})
    assert value not in str(error.value)
