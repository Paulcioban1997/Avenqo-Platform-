"""Model / prediction freshness evaluation (Phase 31.1).

Reuses timestamps the platform already persists — `ModelRegistry.created_at`
(when the active model was trained) and `Dataset.uploaded_at` (when the
tenant's data was last (re)imported for this module) — no new registry, no
invented business SLA.

There is no existing platform-wide freshness policy, so this module defines
a small CONFIGURABLE TECHNICAL default (not a contractual/commercial
promise): a model is considered "stale" once older than
`ai_freshness_stale_after_days` (default 7 days) or once newer tenant data
has been imported since training, and "expired" once older than
`ai_freshness_expired_after_days` (default 30 days). Both are overridable via
`Settings`/environment — see docs/ai-predictive-copilot.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Dataset, DatasetProfile, ModelRegistry
from shared.ai_engine.contracts import TenantContext

FreshnessStatus = Literal["fresh", "stale", "expired", "unknown"]

DEFAULT_STALE_AFTER_DAYS = 7
DEFAULT_EXPIRED_AFTER_DAYS = 30
DEFAULT_BLOCK_ON_EXPIRED = True


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    stale_after: timedelta = timedelta(days=DEFAULT_STALE_AFTER_DAYS)
    expired_after: timedelta = timedelta(days=DEFAULT_EXPIRED_AFTER_DAYS)
    block_on_expired: bool = DEFAULT_BLOCK_ON_EXPIRED


@dataclass(frozen=True, slots=True)
class FreshnessResult:
    status: FreshnessStatus
    data_as_of: datetime | None
    model_trained_at: datetime | None

    def to_safe_dict(self) -> dict[str, str | None]:
        """Business-safe representation: dates only, never a path/filename/model id."""

        return {
            "status": self.status,
            "data_as_of": self.data_as_of.isoformat() if self.data_as_of else None,
            "model_trained_at": self.model_trained_at.isoformat() if self.model_trained_at else None,
        }


def policy_from_settings(settings: object) -> FreshnessPolicy:
    return FreshnessPolicy(
        stale_after=timedelta(days=getattr(settings, "ai_freshness_stale_after_days", DEFAULT_STALE_AFTER_DAYS)),
        expired_after=timedelta(days=getattr(settings, "ai_freshness_expired_after_days", DEFAULT_EXPIRED_AFTER_DAYS)),
        block_on_expired=getattr(settings, "ai_freshness_block_on_expired", DEFAULT_BLOCK_ON_EXPIRED),
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_freshness_inputs(
    session: Session, tenant: TenantContext, module_code: str, task_code: str
) -> tuple[datetime | None, datetime | None]:
    """Reads existing timestamps only — always scoped to `tenant.company_id`."""

    model_row = session.scalar(
        select(ModelRegistry).where(
            ModelRegistry.company_id == tenant.company_id,
            ModelRegistry.module_code == module_code,
            ModelRegistry.task_code == task_code,
            ModelRegistry.is_active.is_(True),
        )
    )
    model_trained_at = model_row.created_at if model_row is not None else None

    dataset = session.scalar(
        select(Dataset)
        .join(DatasetProfile, DatasetProfile.dataset_id == Dataset.id)
        .where(Dataset.company_id == tenant.company_id, DatasetProfile.module_code == module_code)
        .order_by(Dataset.uploaded_at.desc())
    )
    dataset_updated_at = dataset.uploaded_at if dataset is not None else None
    return model_trained_at, dataset_updated_at


def evaluate_freshness(
    model_trained_at: datetime | None,
    dataset_updated_at: datetime | None,
    policy: FreshnessPolicy,
    now: datetime | None = None,
) -> FreshnessResult:
    """Normalizes model/data timestamps into a `fresh`/`stale`/`expired`/`unknown` status.

    `unknown` (no trained_at available, e.g. a historical model row) never
    blocks anything — it is surfaced as-is, never assumed to be `fresh`.
    """

    trained_at = _as_utc(model_trained_at)
    data_at = _as_utc(dataset_updated_at)
    if trained_at is None:
        return FreshnessResult(status="unknown", data_as_of=data_at, model_trained_at=None)

    reference_now = _as_utc(now) or datetime.now(timezone.utc)
    age = reference_now - trained_at
    newer_data_imported = data_at is not None and data_at > trained_at

    status: FreshnessStatus
    if age > policy.expired_after:
        status = "expired"
    elif age > policy.stale_after or newer_data_imported:
        status = "stale"
    else:
        status = "fresh"

    return FreshnessResult(status=status, data_as_of=data_at or trained_at, model_trained_at=trained_at)
