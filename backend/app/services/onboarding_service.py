"""Gère le questionnaire d'onboarding d'une entreprise, scopé au tenant.

Réutilise directement `Company`/`CompanyOnboarding` (relation 1-1) plutôt que
de créer une structure de progression dupliquée — voir docs onboarding.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models import Company, CompanyModule, CompanyOnboarding, Module
from backend.app.models.base import CompanyModuleStatus, OnboardingStatus
from backend.app.schemas.onboarding import OnboardingStatusResponse, OnboardingSubmitRequest
from payments.plans import MODULE_NAMES, get_plan
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
        company = self._session.get(Company, tenant.company_id)
        if company is None:
            return ()
        plan = get_plan(company.subscription_plan)
        now = datetime.now(timezone.utc)
        unavailable: list[str] = []
        selected_count = 0
        for code in dict.fromkeys(module_codes):
            if code not in MODULE_NAMES:
                continue
            if not plan.allows_module(code):
                unavailable.append(code)
                continue
            if (
                plan.max_selectable_modules is not None
                and selected_count >= plan.max_selectable_modules
            ):
                unavailable.append(code)
                continue
            selected_count += 1
            module = self._session.scalar(select(Module).where(Module.code == code))
            if module is None:
                module = Module(name=MODULE_NAMES[code], code=code)
                self._session.add(module)
                self._session.flush()
            company_module = self._session.scalar(
                select(CompanyModule).where(
                    CompanyModule.company_id == tenant.company_id,
                    CompanyModule.module_id == module.id,
                )
            )
            if company_module is None:
                self._session.add(
                    CompanyModule(
                        company_id=tenant.company_id,
                        module_id=module.id,
                        activated_at=now,
                        status=CompanyModuleStatus.ACTIVE,
                    )
                )
            else:
                company_module.status = CompanyModuleStatus.ACTIVE
                company_module.activated_at = now
                company_module.expires_at = None
        return tuple(unavailable)

    def _active_module_codes(self, tenant: TenantContext) -> tuple[str, ...]:
        now = datetime.now(timezone.utc)
        codes = self._session.execute(
            select(Module.code)
            .join(CompanyModule, CompanyModule.module_id == Module.id)
            .where(
                CompanyModule.company_id == tenant.company_id,
                CompanyModule.status == CompanyModuleStatus.ACTIVE,
                CompanyModule.activated_at <= now,
                or_(CompanyModule.expires_at.is_(None), CompanyModule.expires_at > now),
            )
        ).scalars().all()
        return tuple(codes)

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
