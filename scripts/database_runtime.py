"""Resolve operational database credentials exclusively from the environment."""
from collections.abc import Mapping
import os

from sqlalchemy.engine import make_url


def require_database_url(environ: Mapping[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    value = (values.get("DATABASE_URL") or values.get("DATABASE_PUBLIC_URL") or "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL or DATABASE_PUBLIC_URL is required; no fallback credentials.")
    try:
        parsed = make_url(value)
        if parsed.get_backend_name() not in {"postgresql", "postgres", "sqlite"}:
            raise ValueError()
    except Exception:
        raise RuntimeError("Invalid operational database configuration.") from None
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    return value
