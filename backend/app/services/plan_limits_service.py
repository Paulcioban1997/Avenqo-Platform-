"""Server-side enforcement of per-plan capacity limits (users, sites, Voice).

Plan values come from ``payments.plans``; an Enterprise contract overrides them through
``EnterpriseOverride.quota_overrides`` using the same keys (``max_users``, ``max_sites``,
``max_voice_agents``, ``max_concurrent_calls``). ``None`` means no catalogue cap.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from backend.app.models import BillingAccount, Company, CompanyMembership, EmployeeInvitation, User
from backend.app.models.enterprise_override import EnterpriseOverride
from payments import get_plan

LIMIT_KEYS = ("max_users", "max_sites", "max_voice_agents", "max_concurrent_calls")


class PlanLimitReached(ValueError):
    def __init__(self, limit_key: str, limit: int, plan_code: str) -> None:
        self.limit_key = limit_key
        self.limit = limit
        self.plan_code = plan_code
        super().__init__(f"Plan limit reached: {limit_key}={limit} for plan {plan_code}")


@dataclass(frozen=True, slots=True)
class PlanLimits:
    plan_code: str
    max_users: int | None
    max_sites: int | None
    max_voice_agents: int | None
    max_concurrent_calls: int | None

    def get(self, key: str) -> int | None:
        return getattr(self, key)


class PlanLimitsService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def limits_for(self, company_id: UUID) -> PlanLimits:
        company = self._session.get(Company, company_id)
        if company is None:
            raise ValueError("Company not found")
        account = self._session.scalar(
            select(BillingAccount).where(BillingAccount.company_id == company_id)
        )
        plan = get_plan(account.plan_code if account is not None else company.subscription_plan)
        values = {key: getattr(plan, key) for key in LIMIT_KEYS}
        override = self._session.scalar(
            select(EnterpriseOverride).where(EnterpriseOverride.company_id == company_id)
        )
        for key, value in ((override.quota_overrides or {}) if override else {}).items():
            if key in values and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                values[key] = value
        return PlanLimits(plan_code=plan.code.value, **values)

    def active_user_ids(self, company_id: UUID) -> set[UUID]:
        """Seats consumed: active non-platform users whose primary or explicit membership is this company."""
        primary = self._session.scalars(
            select(User.id).where(
                User.company_id == company_id,
                User.is_active.is_(True),
                User.is_platform_admin.is_(False),
            )
        )
        members = self._session.scalars(
            select(User.id)
            .join(CompanyMembership, CompanyMembership.user_id == User.id)
            .where(
                CompanyMembership.company_id == company_id,
                CompanyMembership.is_active.is_(True),
                User.is_active.is_(True),
                User.is_platform_admin.is_(False),
            )
        )
        return set(primary) | set(members)

    def pending_invitation_count(self, company_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        rows = self._session.scalars(
            select(EmployeeInvitation).where(
                EmployeeInvitation.company_id == company_id,
                EmployeeInvitation.accepted_at.is_(None),
                EmployeeInvitation.revoked_at.is_(None),
            )
        )
        count = 0
        for row in rows:
            expires = row.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires > now:
                count += 1
        return count

    def ensure_user_capacity(self, company_id: UUID, *, adding: int = 1) -> PlanLimits:
        self._lock(company_id, "users")
        limits = self.limits_for(company_id)
        used = len(self.active_user_ids(company_id)) + self.pending_invitation_count(company_id)
        if limits.max_users is not None and used + adding > limits.max_users:
            raise PlanLimitReached("max_users", limits.max_users, limits.plan_code)
        return limits

    def ensure_capacity(self, company_id: UUID, limit_key: str, *, current: int, adding: int = 1) -> PlanLimits:
        self._lock(company_id, limit_key)
        limits = self.limits_for(company_id)
        limit = limits.get(limit_key)
        if limit is not None and current + adding > limit:
            raise PlanLimitReached(limit_key, limit, limits.plan_code)
        return limits

    def _lock(self, company_id: UUID, scope: str) -> None:
        if self._session.get_bind().dialect.name == "postgresql":
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"plan_limit:{scope}:{company_id}"},
            )
