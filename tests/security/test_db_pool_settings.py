from backend.app.config.settings import Settings


def test_db_pool_defaults_stay_conservative() -> None:
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    assert settings.db_pool_size == 10
    assert settings.db_max_overflow == 20


def test_db_pool_can_be_raised_via_env(monkeypatch) -> None:
    monkeypatch.setenv("AVENQO_DB_POOL_SIZE", "40")
    monkeypatch.setenv("AVENQO_DB_MAX_OVERFLOW", "40")
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    assert settings.db_pool_size == 40
    assert settings.db_max_overflow == 40
