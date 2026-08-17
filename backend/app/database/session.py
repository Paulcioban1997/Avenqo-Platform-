"""Moteur et sessions SQLAlchemy de Avenqo."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import get_settings
from backend.app.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _build_engine():
    settings = get_settings()
    database_url = settings.database_url
    if database_url.startswith("sqlite:///"):
        database_path = Path(database_url.removeprefix("sqlite:///"))
        if not database_path.is_absolute():
            database_path = PROJECT_ROOT / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{database_path.as_posix()}"
    connect_args = (
        {"check_same_thread": False}
        if database_url.startswith("sqlite")
        else {}
    )
    return create_engine(database_url, connect_args=connect_args)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_database_tables() -> None:
    """CrÃ©e les tables en dÃ©veloppement avant l'arrivÃ©e des migrations."""

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Fournit une session courte Ã  une requÃªte FastAPI."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_session_factory() -> sessionmaker:
    """Expose la sessionmaker elle-mÃªme pour les tÃ¢ches de fond (hors requÃªte FastAPI).

    Les tÃ¢ches de fond (`BackgroundTasks`) ne passent pas par l'injection de
    dÃ©pendances FastAPI : elles doivent ouvrir leur propre session Ã  l'appel.
    Cette dÃ©pendance est surchargeable dans les tests comme `get_db`.
    """

    return SessionLocal
