"""Avenqo Admin Command Center (Phase 33) : lecture/gestion plateforme, cross-tenant.

Réservé aux comptes `platform_admin` (voir `require_platform_admin`). N'expose
jamais le contenu métier privé d'un tenant (données de ventes, clients,
datasets) — uniquement des métadonnées de facturation/usage/santé déjà
considérées sûres pour un administrateur plateforme.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.ai.llm.health import ProviderHealthRegistry
from backend.app.ai.usage.service import AIUsageService
from backend.app.models import (
    BillingAccount,
    Company,
    Dataset,
    EnterpriseOverride,
    ModelRegistry,
    User,
)
from backend.app.services.audit_log_service import AuditLogService

_ACTIVE_STATUSES = {"active", "trialing"}
_PAST_DUE_STATUSES = {"past_due", "unpaid", "incomplete"}


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    total_companies: int
    companies_by_plan: dict[str, int]
    new_companies_last_30_days: int
    active_subscriptions: int
    past_due_subscriptions: int
    ai_requests_current_period: int
    provider_status: dict[str, str]


@dataclass(frozen=True, slots=True)
class CompanyDirectoryEntry:
    id: UUID
    name: str
    country: str
    joined_at: datetime
    plan_code: str
    subscription_status: str
    ai_requests_current_period: int
    monthly_credits: int | None
    monthly_credits_remaining: int | None
    purchased_credits_remaining: int
    total_credits_remaining: int | None
    has_connected_data_source: bool


@dataclass(frozen=True, slots=True)
class CompanyDetail:
    id: UUID
    name: str
    country: str
    joined_at: datetime
    plan_code: str
    subscription_status: str
    cancel_at_period_end: bool
    current_period_end: datetime | None
    ai_requests_current_period: int
    monthly_credits: int | None
    monthly_credits_remaining: int | None
    purchased_credits_remaining: int
    total_credits_remaining: int | None
    users_count: int
    datasets_count: int
    trained_model_count: int
    enterprise_override: dict[str, Any] | None


class AdminService:
    """Vues et actions cross-tenant réservées à l'équipe Avenqo."""

    def __init__(
        self,
        db: Session,
        usage_service: AIUsageService,
        health_registry: ProviderHealthRegistry,
        audit_log: AuditLogService,
    ) -> None:
        self._db = db
        self._usage_service = usage_service
        self._health_registry = health_registry
        self._audit_log = audit_log

    def dashboard(self) -> DashboardSummary:
        companies = list(self._db.scalars(select(Company)))
        by_plan: dict[str, int] = {}
        for company in companies:
            by_plan[company.subscription_plan] = by_plan.get(company.subscription_plan, 0) + 1
        threshold = datetime.now(timezone.utc) - timedelta(days=30)
        new_companies = sum(1 for company in companies if self._aware(company.created_at) >= threshold)

        accounts = list(self._db.scalars(select(BillingAccount)))
        active = sum(1 for account in accounts if account.status in _ACTIVE_STATUSES)
        past_due = sum(1 for account in accounts if account.status in _PAST_DUE_STATUSES)

        total_ai_requests = 0
        period = self._usage_service.current_billing_period()
        for company in companies:
            usage = self._usage_service.get_usage(company.id, company.subscription_plan)
            if usage.billing_period == period:
                total_ai_requests += usage.ai_requests_count

        return DashboardSummary(
            total_companies=len(companies),
            companies_by_plan=by_plan,
            new_companies_last_30_days=new_companies,
            active_subscriptions=active,
            past_due_subscriptions=past_due,
            ai_requests_current_period=total_ai_requests,
            provider_status=dict(self._health_registry.snapshot()),
        )

    def company_directory(self) -> list[CompanyDirectoryEntry]:
        companies = list(self._db.scalars(select(Company).order_by(Company.created_at.desc())))
        entries: list[CompanyDirectoryEntry] = []
        for company in companies:
            account = self._db.scalar(
                select(BillingAccount).where(BillingAccount.company_id == company.id)
            )
            usage = self._usage_service.get_usage(company.id, company.subscription_plan)
            credit_balance = self._usage_service.get_credit_balance(
                company.id, company.subscription_plan
            )
            has_dataset = self._db.scalar(
                select(Dataset).where(Dataset.company_id == company.id).limit(1)
            )
            entries.append(
                CompanyDirectoryEntry(
                    id=company.id,
                    name=company.name,
                    country=company.country,
                    joined_at=self._aware(company.created_at),
                    plan_code=company.subscription_plan,
                    subscription_status=account.status if account else "inactive",
                    ai_requests_current_period=usage.ai_requests_count,
                    monthly_credits=credit_balance["monthly_included"],
                    monthly_credits_remaining=credit_balance["monthly_remaining"],
                    purchased_credits_remaining=int(credit_balance["purchased_remaining"]),
                    total_credits_remaining=credit_balance["total_remaining"],
                    has_connected_data_source=has_dataset is not None,
                )
            )
        return entries

    def company_detail(self, company_id: UUID) -> CompanyDetail | None:
        company = self._db.get(Company, company_id)
        if company is None:
            return None
        account = self._db.scalar(select(BillingAccount).where(BillingAccount.company_id == company_id))
        usage = self._usage_service.get_usage(company_id, company.subscription_plan)
        credits = self._usage_service.get_credit_balance(company_id, company.subscription_plan)
        users_count = self._db.scalar(
            select(func.count()).select_from(User).where(User.company_id == company_id)
        ) or 0
        datasets_count = self._db.scalar(
            select(func.count()).select_from(Dataset).where(Dataset.company_id == company_id)
        ) or 0
        trained_model_count = self._db.scalar(
            select(func.count()).select_from(ModelRegistry).where(ModelRegistry.company_id == company_id)
        ) or 0
        override = self._db.scalar(
            select(EnterpriseOverride).where(EnterpriseOverride.company_id == company_id)
        )
        return CompanyDetail(
            id=company.id,
            name=company.name,
            country=company.country,
            joined_at=self._aware(company.created_at),
            plan_code=company.subscription_plan,
            subscription_status=account.status if account else "inactive",
            cancel_at_period_end=account.cancel_at_period_end if account else False,
            current_period_end=account.current_period_end if account else None,
            ai_requests_current_period=usage.ai_requests_count,
            monthly_credits=credits["monthly_included"],
            monthly_credits_remaining=credits["monthly_remaining"],
            purchased_credits_remaining=int(credits["purchased_remaining"]),
            total_credits_remaining=credits["total_remaining"],
            users_count=int(users_count),
            datasets_count=int(datasets_count),
            trained_model_count=int(trained_model_count),
            enterprise_override=(
                {
                    "quota_overrides": override.quota_overrides,
                    "capability_overrides": override.capability_overrides,
                    "notes": override.notes,
                }
                if override is not None
                else None
            ),
        )

    def set_enterprise_override(
        self,
        *,
        actor_user_id: UUID,
        company_id: UUID,
        quota_overrides: dict[str, int | None],
        capability_overrides: dict[str, bool],
        notes: str | None,
    ) -> EnterpriseOverride:
        company = self._db.get(Company, company_id)
        if company is None:
            raise ValueError("Company not found")
        override = self._db.scalar(
            select(EnterpriseOverride).where(EnterpriseOverride.company_id == company_id)
        )
        if override is None:
            override = EnterpriseOverride(company_id=company_id)
            self._db.add(override)
        override.quota_overrides = quota_overrides
        override.capability_overrides = capability_overrides
        override.notes = notes
        self._db.commit()
        self._audit_log.record(
            actor_user_id=actor_user_id,
            action="enterprise_override.set",
            target_type="company",
            target_id=str(company_id),
            company_id=company_id,
            metadata={
                "quota_metrics": sorted(quota_overrides.keys()),
                "capability_metrics": sorted(capability_overrides.keys()),
            },
        )
        return override

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
