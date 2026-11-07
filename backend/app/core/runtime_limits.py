"""Align HTTP sync threads with the SQLAlchemy pool so requests queue in asyncio, not in PostgreSQL."""

from __future__ import annotations


def postgres_pool_cap(pool_size: int, max_overflow: int) -> int:
    return max(1, int(pool_size) + int(max_overflow))


def effective_http_sync_thread_limit(
    requested: int,
    *,
    pool_size: int,
    max_overflow: int,
    database_url: str,
) -> int:
    """Cap Starlette/anyio worker threads at the PostgreSQL pool ceiling.

    Extra threads above pool_size+max_overflow only wait on QueuePool and
    inflate ``pool_timeout`` errors without raising true query concurrency.
    SQLite tests keep the requested limiter so local suites stay unchanged.
    """

    limit = max(1, int(requested))
    if str(database_url).startswith("sqlite"):
        return limit
    return min(limit, postgres_pool_cap(pool_size, max_overflow))


def apply_http_sync_thread_limit(limit: int) -> int:
    tokens = max(1, int(limit))
    try:
        from anyio import to_thread

        limiter = to_thread.current_default_thread_limiter()
        limiter.total_tokens = tokens
        return int(limiter.total_tokens)
    except Exception:
        # Lifespan always has an event loop. Unit tests may call this cold.
        return tokens
