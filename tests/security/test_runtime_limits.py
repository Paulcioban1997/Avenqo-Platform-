from backend.app.config.settings import Settings
from backend.app.core.runtime_limits import (
    apply_http_sync_thread_limit,
    effective_http_sync_thread_limit,
    postgres_pool_cap,
)


def test_postgres_threads_are_capped_to_pool_ceiling() -> None:
    assert postgres_pool_cap(16, 16) == 32
    assert (
        effective_http_sync_thread_limit(
            80,
            pool_size=16,
            max_overflow=16,
            database_url="postgresql+psycopg2://avenqo_app@127.0.0.1/avenqo",
        )
        == 32
    )


def test_sqlite_keeps_requested_thread_limit() -> None:
    assert (
        effective_http_sync_thread_limit(
            40,
            pool_size=10,
            max_overflow=20,
            database_url="sqlite:///:memory:",
        )
        == 40
    )


def test_pool_timeout_defaults_stay_conservative() -> None:
    settings = Settings(AUTH_JWT_SECRET="a" * 32)
    assert settings.db_pool_size == 10
    assert settings.db_max_overflow == 20
    assert settings.db_pool_timeout == 5.0
    assert settings.http_sync_thread_limit == 40
    assert settings.db_statement_timeout_ms == 15000
    assert settings.db_idle_in_transaction_timeout_ms == 60000


def test_apply_http_sync_thread_limit_sets_anyio_tokens() -> None:
    applied = apply_http_sync_thread_limit(12)
    assert applied == 12
    apply_http_sync_thread_limit(40)
