"""Tenant-scoped business module entitlement policy and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models import BillingAccount, Company, CompanyModule, CompanyModuleStatus, Module
from modules.registry import (
    BUSINESS_MODULE_REGISTRY,
    BusinessModuleDefinition,
    ModuleAvailability,
)
from payments import SubscriptionPlan, get_plan
from shared.ai_engine.contracts import TenantContext


class ModuleEntitlementError(ValueError):
    pass


class ModuleLimitReached(ModuleEntitlementError):
    pass


class ModuleUnavailable(ModuleEntitlementError):
    pass


class ModuleUpgradeRequired(ModuleEntitlementError):
    pass


class ModuleEntitlementState(StrEnum):
    ACTIVE = "active"
    AVAILABLE = "available"
    LIMIT_REACHED = "limit_reached"
    UPGRADE_REQUIRED = "upgrade_required"
    COMING_SOON = "coming_soon"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ModuleEntitlement:
    key: str
    display_name: str
    description: str
    availability: str
    active: bool
    state: ModuleEntitlementState
    premium: bool
    category: str
    credit_multiplier: float


@dataclass(frozen=True, slots=True)
class CompanyEntitlements:
    company_id: UUID
    plan_code: str
    active_modules: tuple[str, ...]
    module_limit: int | None
    remaining_module_slots: int | None
    modules: tuple[ModuleEntitlement, ...]


class ModuleEntitlementService:
    def __init__(
        self,
        session: Session,
        *,
        registry: tuple[BusinessModuleDefinition, ...] = BUSINESS_MODULE_REGISTRY,
        additional_module_slots: int = 0,
    ) -> None:
        self._session = session
        self._registry = registry
        self._by_key = {module.key: module for module in registry}
        self._additional_module_slots = max(additional_module_slots, 0)

    def get_company_plan(self, tenant: TenantContext) -> SubscriptionPlan:
        company = self._company(tenant)
        account = self._session.scalar(
            select(BillingAccount).where(BillingAccount.company_id == tenant.company_id)
        )
        return get_plan(account.plan_code if account is not None else company.subscription_plan)

    def get_active_modules(self, tenant: TenantContext) -> tuple[str, ...]:
        plan = self.get_company_plan(tenant)
        stored = set(self._stored_active_module_keys(tenant))
        return tuple(
            definition.key
            for definition in self._registry
            if definition.key in stored
            and definition.is_available
            and plan.allows_module(definition.key)
        )

    def get_module_limit(self, tenant: TenantContext) -> int | None:
        limit = self.get_company_plan(tenant).max_selectable_modules
        return None if limit is None else limit + self._additional_module_slots

    def get_remaining_module_slots(self, tenant: TenantContext) -> int | None:
        limit = self.get_module_limit(tenant)
        if limit is None:
            return None
        return max(limit - len(self.get_active_modules(tenant)), 0)

    def can_activate_module(self, tenant: TenantContext, module_key: str) -> bool:
        return self._state(tenant, module_key) in {
            ModuleEntitlementState.ACTIVE,
            ModuleEntitlementState.AVAILABLE,
        }

    def activate_module(self, tenant: TenantContext, module_key: str) -> CompanyEntitlements:
        state = self._state(tenant, module_key)
        if state == ModuleEntitlementState.ACTIVE:
            return self.summary(tenant)
        if state == ModuleEntitlementState.LIMIT_REACHED:
            limit = self.get_module_limit(tenant)
            raise ModuleLimitReached(
                f"Module limit reached. Your current plan supports {limit} active modules."
            )
        if state == ModuleEntitlementState.UPGRADE_REQUIRED:
            raise ModuleUpgradeRequired("Upgrade required to activate this module.")
        if state in {ModuleEntitlementState.COMING_SOON, ModuleEntitlementState.UNAVAILABLE}:
            raise ModuleUnavailable("This module is not available for activation.")

        definition = self._by_key[module_key]
        module = self._session.scalar(select(Module).where(Module.code == module_key))
        if module is None:
            module = Module(
                name=definition.display_name,
                code=definition.key,
                description=definition.description,
            )
            self._session.add(module)
            self._session.flush()
        entitlement = self._session.scalar(
            select(CompanyModule).where(
                CompanyModule.company_id == tenant.company_id,
                CompanyModule.module_id == module.id,
            )
        )
        now = datetime.now(timezone.utc)
        if entitlement is None:
            entitlement = CompanyModule(
                company_id=tenant.company_id,
                module_id=module.id,
                activated_at=now,
                status=CompanyModuleStatus.ACTIVE,
            )
            self._session.add(entitlement)
        else:
            entitlement.status = CompanyModuleStatus.ACTIVE
            entitlement.activated_at = now
            entitlement.expires_at = None
        self._session.flush()
        return self.summary(tenant)

    def deactivate_module(self, tenant: TenantContext, module_key: str) -> CompanyEntitlements:
        entitlement = self._session.scalar(
            select(CompanyModule)
            .join(Module, CompanyModule.module_id == Module.id)
            .where(
                CompanyModule.company_id == tenant.company_id,
                Module.code == module_key,
            )
        )
        if entitlement is not None:
            entitlement.status = CompanyModuleStatus.INACTIVE
            entitlement.expires_at = None
            self._session.flush()
        return self.summary(tenant)

    def can_use_module(self, tenant: TenantContext, module_key: str) -> bool:
        return module_key in self.get_active_modules(tenant)

    def summary(self, tenant: TenantContext) -> CompanyEntitlements:
        plan = self.get_company_plan(tenant)
        active_modules = self.get_active_modules(tenant)
        limit = self.get_module_limit(tenant)
        remaining = None if limit is None else max(limit - len(active_modules), 0)
        modules = tuple(
            ModuleEntitlement(
                key=definition.key,
                display_name=definition.display_name,
                description=definition.description,
                availability=definition.availability.value,
                active=definition.key in active_modules,
                state=self._state(tenant, definition.key),
                premium=definition.premium,
                category=definition.category,
                credit_multiplier=definition.credit_multiplier,
            )
            for definition in self._registry
        )
        return CompanyEntitlements(
            company_id=tenant.company_id,
            plan_code=plan.code.value,
            active_modules=active_modules,
            module_limit=limit,
            remaining_module_slots=remaining,
            modules=modules,
        )

    def _state(self, tenant: TenantContext, module_key: str) -> ModuleEntitlementState:
        definition = self._by_key.get(module_key)
        if definition is None or definition.availability == ModuleAvailability.UNAVAILABLE:
            return ModuleEntitlementState.UNAVAILABLE
        if definition.availability == ModuleAvailability.COMING_SOON:
            return ModuleEntitlementState.COMING_SOON
        plan = self.get_company_plan(tenant)
        if not plan.allows_module(module_key):
            return ModuleEntitlementState.UPGRADE_REQUIRED
        if module_key in self.get_active_modules(tenant):
            return ModuleEntitlementState.ACTIVE
        if self.get_remaining_module_slots(tenant) == 0:
            return ModuleEntitlementState.LIMIT_REACHED
        return ModuleEntitlementState.AVAILABLE

    def _stored_active_module_keys(self, tenant: TenantContext) -> tuple[str, ...]:
        now = datetime.now(timezone.utc)
        return tuple(self._session.scalars(
            select(Module.code)
            .join(CompanyModule, CompanyModule.module_id == Module.id)
            .where(
                CompanyModule.company_id == tenant.company_id,
                CompanyModule.status == CompanyModuleStatus.ACTIVE,
                CompanyModule.activated_at <= now,
                or_(CompanyModule.expires_at.is_(None), CompanyModule.expires_at > now),
                Module.is_active.is_(True),
            )
        ))

    def _company(self, tenant: TenantContext) -> Company:
        company = self._session.get(Company, tenant.company_id)
        if company is None:
            raise ModuleEntitlementError("Company not found")
        return company


__all__ = [
    "CompanyEntitlements",
    "ModuleEntitlement",
    "ModuleEntitlementError",
    "ModuleEntitlementService",
    "ModuleEntitlementState",
    "ModuleLimitReached",
    "ModuleUnavailable",
    "ModuleUpgradeRequired",
]