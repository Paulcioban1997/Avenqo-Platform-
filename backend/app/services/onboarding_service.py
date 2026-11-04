"""Gère le questionnaire d'onboarding d'une entreprise, scopé au tenant.

Réutilise directement `Company`/`CompanyOnboarding` (relation 1-1) plutôt que
de créer une structure de progression dupliquée. Intègre la personnalisation
visuelle White-Label (logo, couleurs) et le provisionnement des contrats légaux.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    CommerceConnection,
    Company,
    CompanyContract,
    CompanyOnboarding,
    Dataset,
    EmployeeResponsibility,
    User,
    VoiceBusinessConfig,
)
from backend.app.models.base import OnboardingStatus
from backend.app.schemas.onboarding import OnboardingDraftRequest, OnboardingStatusResponse, OnboardingSubmitRequest
from .contract_signature_service import ContractSignatureService
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
        record.current_step = request.current_step or "complete"
        record.status = OnboardingStatus.COMPLETED
        record.completed_at = datetime.now(timezone.utc)

        # Enregistrer la personnalisation White-Label dans draft_payload
        draft = dict(record.draft_payload or {})
        if request.company_logo_url:
            draft["company_logo_url"] = request.company_logo_url
        if request.theme_mode:
            draft["theme_mode"] = request.theme_mode
        if request.brand_color:
            draft["brand_color"] = request.brand_color
        record.draft_payload = draft

        # Activation des modules sélectionnés selon les limites du plan
        unavailable = self.activate_selected_modules(tenant, request.selected_modules)

        # Provisionner les contrats obligatoires pour signature immédiate
        company = self._session.get(Company, tenant.company_id)
        if company:
            try:
                ContractSignatureService(self._session).ensure_contracts_for_company(company)
            except Exception:
                pass

        self._session.commit()
        return self._to_response(record, tenant, unavailable_modules=unavailable)

    def save_draft(self, tenant: TenantContext, request: OnboardingDraftRequest) -> OnboardingStatusResponse:
        record = self._get_or_create(tenant)
        if record.status == OnboardingStatus.COMPLETED:
            return self._to_response(record, tenant)
        record.current_step = request.current_step
        record.business_goals = list(request.business_goals)
        record.current_tools = list(request.current_tools)
        record.team_size = request.team_size
        record.refined_industry = request.refined_industry

        draft = dict(record.draft_payload or {})
        draft["selected_modules"] = list(request.selected_modules)
        if request.company_logo_url:
            draft["company_logo_url"] = request.company_logo_url
        if request.theme_mode:
            draft["theme_mode"] = request.theme_mode
        if request.brand_color:
            draft["brand_color"] = request.brand_color
        record.draft_payload = draft

        self._session.commit()
        return self._to_response(record, tenant)

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
            self._session.flush()
        return record

    def activate_selected_modules(
        self, tenant: TenantContext, module_codes: tuple[str, ...], *, auto_init_voice: bool = True
    ) -> tuple[str, ...]:
        """Active les modules optionnels choisis, en respectant le plan."""
        if not module_codes:
            return ()
        entitlements = ModuleEntitlementService(self._session)
        unavailable: list[str] = []
        for code in dict.fromkeys(module_codes):
            if code not in BUSINESS_MODULES_BY_KEY:
                continue
            try:
                entitlements.activate_module(tenant, code, auto_init_voice=auto_init_voice)
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
        company_id = tenant.company_id
        checklist = self._checklist(tenant, record)
        done = sum(1 for item in checklist if item["done"])

        draft = record.draft_payload or {}
        company_logo_url = draft.get("company_logo_url")
        theme_mode = draft.get("theme_mode", "system")
        brand_color = draft.get("brand_color", "#0076FF")

        # Statut des contrats légaux
        pending_count = self._session.scalar(
            select(func.count()).select_from(CompanyContract).where(
                CompanyContract.company_id == company_id,
                CompanyContract.status != "SIGNED",
            )
        ) or 0
        signed_count = self._session.scalar(
            select(func.count()).select_from(CompanyContract).where(
                CompanyContract.company_id == company_id,
                CompanyContract.status == "SIGNED",
            )
        ) or 0

        return OnboardingStatusResponse(
            status=record.status,
            business_goals=tuple(record.business_goals or ()),
            current_tools=tuple(record.current_tools or ()),
            team_size=record.team_size,
            refined_industry=record.refined_industry,
            completed_at=record.completed_at,
            activated_modules=self._active_module_codes(tenant),
            unavailable_modules=unavailable_modules,
            current_step=record.current_step,
            progress_percent=int((done / len(checklist)) * 100) if checklist else 0,
            checklist=tuple(checklist),
            company_logo_url=company_logo_url,
            theme_mode=theme_mode,
            brand_color=brand_color,
            contracts_pending_count=int(pending_count),
            contracts_signed_count=int(signed_count),
        )

    def _checklist(self, tenant: TenantContext, record: CompanyOnboarding) -> list[dict]:
        company_id = tenant.company_id
        modules = self._active_module_codes(tenant)
        connectors = self._session.scalar(
            select(func.count()).select_from(CommerceConnection).where(CommerceConnection.company_id == company_id)
        ) or 0
        datasets = self._session.scalar(
            select(func.count()).select_from(Dataset).where(Dataset.company_id == company_id)
        ) or 0
        employees = self._session.scalar(
            select(func.count()).select_from(User).where(User.company_id == company_id)
        ) or 0
        responsibilities = self._session.scalar(
            select(func.count()).select_from(EmployeeResponsibility).where(EmployeeResponsibility.company_id == company_id)
        ) or 0
        voice = self._session.scalar(
            select(func.count()).select_from(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id)
        ) or 0

        # Vérification des contrats signés
        signed_contracts = self._session.scalar(
            select(func.count()).select_from(CompanyContract).where(
                CompanyContract.company_id == company_id,
                CompanyContract.status == "SIGNED",
            )
        ) or 0

        draft = record.draft_payload or {}
        has_customization = bool(draft.get("company_logo_url") or draft.get("brand_color"))

        return [
            {"key": "space", "done": True},
            {"key": "customization", "done": has_customization},
            {"key": "sector", "done": bool(record.refined_industry)},
            {"key": "needs", "done": bool(record.business_goals)},
            {"key": "modules", "done": bool(modules)},
            {"key": "connectors", "done": connectors > 0},
            {"key": "contracts", "done": signed_contracts >= 2},
            {"key": "data", "done": datasets > 0},
            {"key": "employees", "done": employees > 1},
            {"key": "responsibilities", "done": responsibilities > 0},
            {"key": "agents", "done": voice > 0 or "crm" in modules or "retail" in modules},
            {"key": "complete", "done": record.status == OnboardingStatus.COMPLETED},
        ]
