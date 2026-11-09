"""Gère le questionnaire d'onboarding d'une entreprise et le parcours multi-pages.

Réutilise directement `Company`/`CompanyOnboarding` (relation 1-1) plutôt que
de créer une structure de progression dupliquée. Intègre la personnalisation
visuelle White-Label (catalogue des 15 thèmes, 5 approuvés, logo, couleurs)
et le provisionnement des contrats légaux et abonnements.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    BillingAccount,
    CommerceConnection,
    Company,
    CompanyContract,
    CompanyLegalProfile,
    CompanyOnboarding,
    Dataset,
    EmployeeResponsibility,
    User,
    VoiceBusinessConfig,
)
from backend.app.models.base import CompanyStatus, OnboardingStatus
from backend.app.schemas.onboarding import (
    FinalizeOnboardingResponse,
    MultiStepOnboardingStateResponse,
    OnboardingDraftRequest,
    OnboardingStatusResponse,
    OnboardingSubmitRequest,
)
from .contract_signature_service import ContractSignatureService
from backend.app.services.module_entitlement_service import (
    ModuleEntitlementError,
    ModuleEntitlementService,
)
from modules.registry import BUSINESS_MODULES_BY_KEY, BUSINESS_MODULE_REGISTRY
from payments.plans import PLANS, PLANS_BY_CODE, PlanCode
from shared.ai_engine.contracts import TenantContext
from shared.themes.theme_catalog import (
    DEFAULT_THEME_ID,
    get_all_candidate_themes,
    get_theme,
)


ONBOARDING_STEPS_ORDER = [
    "company",
    "modules",
    "design",
    "preview",
    "contracts",
    "subscription",
    "checkout",
    "complete",
]


class OnboardingService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- Méthodes existantes préservées pour compatibilité 100% ---

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
            ContractSignatureService(self._session).ensure_contracts_for_company(company)

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

        signed_contracts = self._session.scalar(
            select(func.count()).select_from(CompanyContract).where(
                CompanyContract.company_id == company_id,
                CompanyContract.status == "SIGNED",
            )
        ) or 0

        draft = record.draft_payload or {}
        has_customization = bool(draft.get("company_logo_url") or draft.get("brand_color") or draft.get("design"))

        return [
            {"key": "space", "done": True},
            {"key": "customization", "done": has_customization},
            {"key": "sector", "done": bool(record.refined_industry or draft.get("company_info", {}).get("industry"))},
            {"key": "needs", "done": bool(record.business_goals or draft.get("company_info", {}).get("description"))},
            {"key": "modules", "done": bool(modules or draft.get("selected_modules"))},
            {"key": "connectors", "done": connectors > 0},
            {"key": "contracts", "done": signed_contracts >= 1 or bool(draft.get("contracts", {}).get("accepted_contract_types"))},
            {"key": "data", "done": datasets > 0},
            {"key": "employees", "done": employees > 1},
            {"key": "responsibilities", "done": responsibilities > 0},
            {"key": "agents", "done": voice > 0 or "crm" in modules or "retail" in modules},
            {"key": "complete", "done": record.status == OnboardingStatus.COMPLETED},
        ]

    # --- Nouvelles méthodes pour le parcours multi-pages (8 étapes) ---

    def get_multistep_state(self, tenant: TenantContext) -> MultiStepOnboardingStateResponse:
        record = self._get_or_create(tenant)
        company = self._session.get(Company, tenant.company_id)
        draft = dict(record.draft_payload or {})

        # Ensure mandatory contracts are provisioned
        if company:
            ContractSignatureService(self._session).ensure_contracts_for_company(company)

        # 1. Company info
        stored_company_info = draft.get("company_info", {})
        owner = self._session.scalar(
            select(User).where(User.company_id == tenant.company_id, User.role.ilike("%owner%"))
        ) or self._session.scalar(select(User).where(User.company_id == tenant.company_id))

        company_info = {
            "commercial_name": stored_company_info.get("commercial_name") or (company.name if company else ""),
            "legal_name": stored_company_info.get("legal_name") or (company.name if company else ""),
            "country": stored_company_info.get("country") or (company.country if company else "Canada"),
            "region": stored_company_info.get("region") or (company.region if company else "Quebec"),
            "timezone": stored_company_info.get("timezone") or (company.timezone if company else "America/Montreal"),
            "industry": stored_company_info.get("industry") or (company.industry if company else "Technologies"),
            "team_size": stored_company_info.get("team_size") or record.team_size or (company.company_size if company else "1-10"),
            "website": stored_company_info.get("website") or (company.website if company else ""),
            "description": stored_company_info.get("description") or (record.business_goals[0] if record.business_goals else ""),
            "authorized_rep_first_name": stored_company_info.get("authorized_rep_first_name") or (owner.first_name if owner else ""),
            "authorized_rep_last_name": stored_company_info.get("authorized_rep_last_name") or (owner.last_name if owner else ""),
            "authorized_rep_title": stored_company_info.get("authorized_rep_title") or "Dirigeant",
        }

        # 2. Modules info
        selected_modules = draft.get("selected_modules") or list(self._active_module_codes(tenant))
        if not selected_modules and record.draft_payload.get("selected_modules"):
            selected_modules = list(record.draft_payload.get("selected_modules"))

        # 3. Design info
        default_theme = get_theme(DEFAULT_THEME_ID)
        stored_design = draft.get("design", {})
        design = {
            "theme_id": stored_design.get("theme_id") or draft.get("theme_id") or default_theme.id,
            "primary_color": stored_design.get("primary_color") or draft.get("brand_color") or default_theme.primary_color,
            "secondary_color": stored_design.get("secondary_color") or default_theme.secondary_color,
            "accent_color": stored_design.get("accent_color") or default_theme.accent_color,
            "mode": stored_design.get("mode") or draft.get("theme_mode") or default_theme.mode,
            "background_style": stored_design.get("background_style") or default_theme.background_style,
            "company_logo_url": stored_design.get("company_logo_url") or draft.get("company_logo_url") or "",
            "company_emblem_url": stored_design.get("company_emblem_url") or "",
            "display_name": stored_design.get("display_name") or (company.name if company else ""),
        }

        # 4. Contracts info
        contracts_rows = self._session.scalars(
            select(CompanyContract).where(CompanyContract.company_id == tenant.company_id)
        ).all()
        mandatory_contracts = [
            {
                "contract_type": c.contract_type,
                "title": c.title,
                "version": c.version,
                "is_mandatory": True,
                "status": c.status,
                "is_signed": c.status == "SIGNED",
            }
            for c in contracts_rows
        ]
        stored_contracts = draft.get("contracts", {})
        accepted_contract_types = stored_contracts.get("accepted_contract_types", [])

        # 5. Subscription info
        plan_code = draft.get("selected_plan", {}).get("plan_code") or (company.subscription_plan if company else "base")
        subscription_account = self._session.scalar(
            select(BillingAccount).where(BillingAccount.company_id == tenant.company_id)
        )
        subscription_status = subscription_account.status if subscription_account else "inactive"
        if company and company.status == CompanyStatus.ACTIVE and subscription_status == "inactive":
            subscription_status = "active"

        # Check completed steps
        completed_steps = []
        if company_info.get("commercial_name") and company_info.get("authorized_rep_first_name"):
            completed_steps.append("company")
        if selected_modules:
            completed_steps.append("modules")
        if design.get("theme_id"):
            completed_steps.append("design")
            completed_steps.append("preview")
        if any(c["is_signed"] for c in mandatory_contracts) or len(accepted_contract_types) >= 1:
            completed_steps.append("contracts")
        if plan_code:
            completed_steps.append("subscription")
        if subscription_status in ("active", "trialing", "verified_test"):
            completed_steps.append("checkout")
        if record.status == OnboardingStatus.COMPLETED:
            completed_steps.append("complete")

        current_step = record.current_step or (completed_steps[-1] if completed_steps else "company")
        if current_step not in ONBOARDING_STEPS_ORDER:
            current_step = "company"

        progress_percent = int((len(completed_steps) / len(ONBOARDING_STEPS_ORDER)) * 100)

        missing_requirements = []
        if "company" not in completed_steps:
            missing_requirements.append("company_info_missing")
        if "modules" not in completed_steps:
            missing_requirements.append("modules_selection_missing")
        if "design" not in completed_steps:
            missing_requirements.append("design_theme_missing")
        if "contracts" not in completed_steps:
            missing_requirements.append("contracts_not_accepted")
        if subscription_status not in ("active", "trialing", "verified_test"):
            missing_requirements.append("subscription_not_active")

        can_finalize = len(missing_requirements) == 0

        return MultiStepOnboardingStateResponse(
            status=record.status.value,
            is_completed=record.status == OnboardingStatus.COMPLETED,
            current_step=current_step,
            progress_percent=progress_percent,
            completed_steps=completed_steps,
            company_info=company_info,
            modules={
                "selected_modules": selected_modules,
                "all_modules": [
                    {
                        "key": m.key,
                        "display_name": m.display_name,
                        "description": m.description,
                        "availability": m.availability.value,
                        "category": m.category,
                        "premium": m.premium,
                    }
                    for m in BUSINESS_MODULE_REGISTRY
                ],
                "central_ai_included": True,
            },
            design=design,
            contracts={
                "mandatory_contracts": mandatory_contracts,
                "accepted_contract_types": accepted_contract_types,
                "accepted_by_name": stored_contracts.get("accepted_by_name"),
                "accepted_by_title": stored_contracts.get("accepted_by_title"),
                "all_mandatory_signed": any(c["is_signed"] for c in mandatory_contracts) or len(accepted_contract_types) >= 1,
            },
            subscription={
                "selected_plan": plan_code,
                "status": subscription_status,
                "plans": [
                    {
                        "code": p.code.value,
                        "name": p.name,
                        "max_selectable_modules": p.max_selectable_modules,
                        "monthly_price_cad": p.monthly_price_cad,
                        "monthly_price_usd": p.monthly_price_usd,
                        "monthly_ai_credits": p.monthly_ai_credits,
                        "max_users": p.max_users,
                        "requires_sales_contact": p.requires_sales_contact,
                    }
                    for p in PLANS
                ],
            },
            candidate_themes=get_all_candidate_themes(),
            can_finalize=can_finalize,
            missing_requirements=missing_requirements,
            completed_at=record.completed_at,
        )

    def update_step(self, tenant: TenantContext, step_id: str, data: dict[str, Any]) -> MultiStepOnboardingStateResponse:
        record = self._get_or_create(tenant)
        company = self._session.get(Company, tenant.company_id)
        draft = dict(record.draft_payload or {})

        record.current_step = step_id

        if step_id == "company":
            company_info = data.get("company_info") or data
            draft["company_info"] = company_info
            if company:
                if company_info.get("commercial_name"):
                    company.name = str(company_info["commercial_name"]).strip()
                if company_info.get("country"):
                    company.country = str(company_info["country"]).strip()
                if company_info.get("timezone"):
                    company.timezone = str(company_info["timezone"]).strip()
                if company_info.get("industry"):
                    company.industry = str(company_info["industry"]).strip()
                    record.refined_industry = company.industry
                if company_info.get("website"):
                    company.website = str(company_info["website"]).strip()
                if company_info.get("team_size"):
                    record.team_size = str(company_info["team_size"]).strip()
                    company.company_size = record.team_size
                if company_info.get("description"):
                    record.business_goals = [str(company_info["description"]).strip()]

            # Sync legal profile if rep info provided
            legal_profile = self._session.scalar(
                select(CompanyLegalProfile).where(CompanyLegalProfile.company_id == tenant.company_id)
            )
            if legal_profile:
                if company_info.get("legal_name"):
                    legal_profile.legal_name = str(company_info["legal_name"]).strip()
                if company_info.get("authorized_rep_first_name"):
                    legal_profile.authorized_representative_first_name = str(company_info["authorized_rep_first_name"]).strip()
                if company_info.get("authorized_rep_last_name"):
                    legal_profile.authorized_representative_last_name = str(company_info["authorized_rep_last_name"]).strip()
                if company_info.get("authorized_rep_title"):
                    legal_profile.authorized_representative_title = str(company_info["authorized_rep_title"]).strip()

        elif step_id == "modules":
            selected = data.get("selected_modules", [])
            draft["selected_modules"] = list(selected)
            if data.get("industry_category"):
                record.refined_industry = str(data["industry_category"]).strip()

        elif step_id == "design":
            design_data = data.get("design") or data
            draft["design"] = design_data
            if design_data.get("company_logo_url"):
                draft["company_logo_url"] = design_data["company_logo_url"]
            if design_data.get("mode"):
                draft["theme_mode"] = design_data["mode"]
            if design_data.get("primary_color"):
                draft["brand_color"] = design_data["primary_color"]
            if design_data.get("theme_id"):
                draft["theme_id"] = design_data["theme_id"]

        elif step_id == "contracts":
            contracts_data = data.get("contracts") or data
            draft["contracts"] = contracts_data
            # Sign any pending contracts in the system
            if company:
                sig_service = ContractSignatureService(self._session)
                sig_service.ensure_contracts_for_company(company)
                pending = self._session.scalars(
                    select(CompanyContract).where(
                        CompanyContract.company_id == tenant.company_id,
                        CompanyContract.status != "SIGNED",
                    )
                ).all()
                for c in pending:
                    c.status = "SIGNED"
                    c.signed_at = datetime.now(timezone.utc)
                    c.accepted_by_name = contracts_data.get("accepted_by_name", "Dirigeant")
                    c.accepted_by_title = contracts_data.get("accepted_by_title", "Représentant")

        elif step_id == "subscription":
            sub_data = data.get("subscription") or data
            draft["selected_plan"] = sub_data
            if company and sub_data.get("plan_code"):
                company.subscription_plan = str(sub_data["plan_code"]).lower()

        elif step_id == "checkout":
            # Stripe checkout step data
            checkout_data = data.get("checkout") or data
            draft["checkout"] = checkout_data

        record.draft_payload = draft
        self._session.commit()
        return self.get_multistep_state(tenant)

    def finalize_onboarding(self, tenant: TenantContext) -> FinalizeOnboardingResponse:
        record = self._get_or_create(tenant)
        company = self._session.get(Company, tenant.company_id)
        if not company:
            raise ValueError("Entreprise introuvable")

        draft = dict(record.draft_payload or {})
        selected_modules = draft.get("selected_modules") or []
        plan_code = (draft.get("selected_plan", {}).get("plan_code") or company.subscription_plan or "base").lower()

        # Reconcile modules with plan limit
        plan_def = PLANS_BY_CODE.get(PlanCode(plan_code)) if plan_code in [p.value for p in PlanCode] else None
        if plan_def and plan_def.max_selectable_modules:
            selected_modules = selected_modules[:plan_def.max_selectable_modules]

        # Activate selected modules
        activated = self.activate_selected_modules(tenant, tuple(selected_modules))

        # Sign contracts if not already signed
        pending_contracts = self._session.scalars(
            select(CompanyContract).where(
                CompanyContract.company_id == tenant.company_id,
                CompanyContract.status != "SIGNED",
            )
        ).all()
        rep_name = draft.get("company_info", {}).get("authorized_rep_first_name", "Authorized")
        for c in pending_contracts:
            c.status = "SIGNED"
            c.signed_at = datetime.now(timezone.utc)
            c.accepted_by_name = rep_name

        # Mark onboarding completed
        record.status = OnboardingStatus.COMPLETED
        record.completed_at = datetime.now(timezone.utc)
        record.current_step = "complete"

        # Ensure company is active
        company.status = CompanyStatus.ACTIVE

        self._session.commit()

        return FinalizeOnboardingResponse(
            success=True,
            status=record.status.value,
            message="Espace Avenqo activé avec succès",
            dashboard_url="/dashboard",
            activated_modules=list(self._active_module_codes(tenant)),
            plan_code=plan_code,
            company_name=company.name,
        )

    def get_tenant_branding(self, tenant: TenantContext) -> dict[str, Any]:
        record = self._get_or_create(tenant)
        company = self._session.get(Company, tenant.company_id)
        draft = dict(record.draft_payload or {})
        default_theme = get_theme(DEFAULT_THEME_ID)
        stored_design = draft.get("design", {})

        return {
            "theme_id": stored_design.get("theme_id") or draft.get("theme_id") or default_theme.id,
            "primary_color": stored_design.get("primary_color") or draft.get("brand_color") or default_theme.primary_color,
            "secondary_color": stored_design.get("secondary_color") or default_theme.secondary_color,
            "accent_color": stored_design.get("accent_color") or default_theme.accent_color,
            "mode": stored_design.get("mode") or draft.get("theme_mode") or default_theme.mode,
            "background_style": stored_design.get("background_style") or default_theme.background_style,
            "company_logo_url": stored_design.get("company_logo_url") or draft.get("company_logo_url") or "",
            "company_emblem_url": stored_design.get("company_emblem_url") or "",
            "display_name": stored_design.get("display_name") or (company.name if company else ""),
            "candidate_themes": get_all_candidate_themes(),
        }

    def update_tenant_branding(self, tenant: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        record = self._get_or_create(tenant)
        company = self._session.get(Company, tenant.company_id)
        draft = dict(record.draft_payload or {})

        reset = data.get("reset", False)
        if reset:
            default_theme = get_theme(DEFAULT_THEME_ID)
            design_data = {
                "theme_id": default_theme.id,
                "primary_color": default_theme.primary_color,
                "secondary_color": default_theme.secondary_color,
                "accent_color": default_theme.accent_color,
                "mode": default_theme.mode,
                "background_style": default_theme.background_style,
                "company_logo_url": "",
                "company_emblem_url": "",
                "display_name": company.name if company else "",
            }
        else:
            current_design = draft.get("design", {})
            design_data = {
                "theme_id": data.get("theme_id") or current_design.get("theme_id") or DEFAULT_THEME_ID,
                "primary_color": data.get("primary_color") or current_design.get("primary_color") or "#0076FF",
                "secondary_color": data.get("secondary_color") or current_design.get("secondary_color") or "#0B132B",
                "accent_color": data.get("accent_color") or current_design.get("accent_color") or "#00D4FF",
                "mode": data.get("mode") or current_design.get("mode") or "dark",
                "background_style": data.get("background_style") or current_design.get("background_style") or "mesh_dark",
                "company_logo_url": data.get("company_logo_url", current_design.get("company_logo_url")),
                "company_emblem_url": data.get("company_emblem_url", current_design.get("company_emblem_url")),
                "display_name": data.get("display_name", current_design.get("display_name")),
            }

        draft["design"] = design_data
        draft["theme_id"] = design_data["theme_id"]
        draft["brand_color"] = design_data["primary_color"]
        draft["theme_mode"] = design_data["mode"]
        draft["company_logo_url"] = design_data["company_logo_url"]

        record.draft_payload = draft
        self._session.commit()
        return self.get_tenant_branding(tenant)
