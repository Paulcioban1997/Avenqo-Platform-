"""Gère le questionnaire d'onboarding d'une entreprise, scopé au tenant.

Réutilise directement `Company`/`CompanyOnboarding` (relation 1-1) plutôt que
de créer une structure de progression dupliquée — voir docs onboarding.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models import CompanyOnboarding
from backend.app.models.base import OnboardingStatus
from backend.app.schemas.onboarding import OnboardingStatusResponse, OnboardingSubmitRequest
from backend.app.services.module_entitlement_service import (
    ModuleEntitlementError,
    ModuleEntitlementService,
)
from modules.registry import BUSINESS_MODULES_BY_KEY
from shared.ai_engine.contracts import TenantContext


class OnboardingService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_status(self, tenant: TenantContext) -> OnboardingStatusResponse:
        return self._to_response(self._get_or_create(tenant), tenant)

    def submit(
        self, tenant: TenantContext, request: OnboardingSubmitRequest
    ) -> OnboardingStatusResponse:
        record = self._get_or_create(tenant)
        record.business_goals = list(request.business_goals)
        record.current_tools = list(request.current_tools)
        record.team_size = request.team_size
        record.refined_industry = request.refined_industry
        record.status = OnboardingStatus.COMPLETED
        record.completed_at = datetime.now(timezone.utc)
        unavailable = self.activate_selected_modules(tenant, request.selected_modules)
        self._session.commit()
        return self._to_response(record, tenant, unavailable_modules=unavailable)

    def skip(self, tenant: TenantContext) -> OnboardingStatusResponse:
        record = self._get_or_create(tenant)
        if record.status == OnboardingStatus.PENDING:
            record.status = OnboardingStatus.SKIPPED
            self._session.commit()
        return self._to_response(record, tenant)

    def _get_or_create(self, tenant: TenantContext) -> CompanyOnboarding:
        record = self._session.get(CompanyOnboarding, tenant.company_id)
        if record is None:
            record = CompanyOnboarding(company_id=tenant.company_id)
            self._session.add(record)
            self._session.commit()
        return record

    def activate_selected_modules(
        self, tenant: TenantContext, module_codes: tuple[str, ...]
    ) -> tuple[str, ...]:
        """Active les modules optionnels choisis, en respectant le plan.

        Ne contourne jamais la facturation : un module hors du plan est
        rapporté dans `unavailable` plutôt qu'activé.
        """
        if not module_codes:
            return ()
        entitlements = ModuleEntitlementService(self._session)
        unavailable: list[str] = []
        for code in dict.fromkeys(module_codes):
            if code not in BUSINESS_MODULES_BY_KEY:
                continue
            try:
                entitlements.activate_module(tenant, code)
            except ModuleEntitlementError:
                unavailable.append(code)
        return tuple(unavailable)

    def _active_module_codes(self, tenant: TenantContext) -> tuple[str, ...]:
        return ModuleEntitlementService(self._session).get_active_modules(tenant)

    def _to_response(
        self,
        record: CompanyOnboarding,
        tenant: TenantContext,
        unavailable_modules: tuple[str, ...] = (),
    ) -> OnboardingStatusResponse:
        return OnboardingStatusResponse(
            status=record.status,
            business_goals=tuple(record.business_goals or ()),
            current_tools=tuple(record.current_tools or ()),
            team_size=record.team_size,
            refined_industry=record.refined_industry,
            completed_at=record.completed_at,
            activated_modules=self._active_module_codes(tenant),
            unavailable_modules=unavailable_modules,
        )
