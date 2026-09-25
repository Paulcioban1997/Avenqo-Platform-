"""Moteur et sessions SQLAlchemy de Avenqo."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import get_settings
from backend.app.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _normalize_sqlite_database_url(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        return database_url

    database_target = database_url.removeprefix("sqlite:///")
    if database_target == ":memory:":
        return database_url

    database_path = Path(database_target)
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{database_path.as_posix()}"


def _build_engine():
    settings = get_settings()
    database_url = settings.database_url
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    database_url = _normalize_sqlite_database_url(database_url)
    connect_args = (
        {"check_same_thread": False}
        if database_url.startswith("sqlite")
        else {}
    )
    engine_kwargs: dict[str, object] = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
    }
    if not database_url.startswith("sqlite"):
        engine_kwargs["pool_size"] = 10
        engine_kwargs["max_overflow"] = 20
        engine_kwargs["pool_recycle"] = 300
        engine_kwargs["pool_reset_on_return"] = "rollback"

    return create_engine(database_url, **engine_kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_database_tables() -> None:
    """Crée les tables en développement avant l'arrivée des migrations."""

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Fournit une session courte à une requête FastAPI."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def get_session_factory() -> sessionmaker:
    """Expose la sessionmaker elle-mÃªme pour les tÃ¢ches de fond (hors requÃªte FastAPI).

    Les tÃ¢ches de fond (`BackgroundTasks`) ne passent pas par l'injection de
    dÃ©pendances FastAPI : elles doivent ouvrir leur propre session Ã  l'appel.
    Cette dÃ©pendance est surchargeable dans les tests comme `get_db`.
    """

    return SessionLocal
