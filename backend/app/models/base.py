from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(_type, _compiler, **_kw):
    # Le type "UUID" donne une affinité NUMERIC à SQLite : un identifiant hexadécimal
    # comme "123e4567..." serait converti en nombre flottant. CHAR(32) garde le texte.
    return "CHAR(32)"


class Base(DeclarativeBase):
    """Classe déclarative commune à tous les modèles SQLAlchemy."""


class TimestampMixin:
    """Ajoute des dates de création et de modification réutilisables."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CompanyStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class UserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    ANALYST = "analyst"
    USER = "user"
    VIEWER = "viewer"


class AccountTokenPurpose(str, Enum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


class CompanyModuleStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
    EXPIRED = "expired"


class DatasetStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    VALIDATED = "validated"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    # Phase 26 — pipeline d'ingestion universelle (formats multiples,
    # mapping sémantique, nettoyage). Conservés en plus des statuts
    # historiques ci-dessus pour ne rien casser du chemin CSV existant.
    PARSING = "parsing"
    MAPPING_REQUIRED = "mapping_required"
    CLEANING = "cleaning"
    READY = "ready"
    INVALID = "invalid"
    FAILED = "failed"


class DatasetVersionStatus(str, Enum):
    UPLOADED = "uploaded"
    VALIDATED = "validated"
    READY = "ready"
    ARCHIVED = "archived"
    FAILED = "failed"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DatasetEvaluationStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    COALESCED = "coalesced"


class OnboardingStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
