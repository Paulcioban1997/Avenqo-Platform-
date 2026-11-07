from backend.app.config.settings import Settings
from backend.app.database.session import _postgres_connect_args


def test_db_pool_defaults_stay_conservative() -> None:
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    assert settings.db_pool_size == 10
    assert settings.db_max_overflow == 20
    assert settings.db_pool_timeout == 5.0


def test_db_pool_can_be_raised_via_env(monkeypatch) -> None:
    monkeypatch.setenv("AVENQO_DB_POOL_SIZE", "40")
    monkeypatch.setenv("AVENQO_DB_MAX_OVERFLOW", "40")
    monkeypatch.setenv("AVENQO_DB_POOL_TIMEOUT", "8")
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    assert settings.db_pool_size == 40
    assert settings.db_max_overflow == 40
    assert settings.db_pool_timeout == 8.0


def test_postgres_connect_args_pin_statement_and_idle_timeouts() -> None:
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    options = _postgres_connect_args(settings)["options"]
    assert "statement_timeout=15000" in options
    assert "idle_in_transaction_session_timeout=60000" in options
