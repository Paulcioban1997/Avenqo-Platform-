"""Reuse company onboarding + CRM; no new parallel configuration database."""
from uuid import UUID
from sqlalchemy import select, text
from backend.app.models import Company, CompanyMembership, User, UserRole, VoiceBusinessConfig
from backend.app.models.company_onboarding import CompanyOnboarding
from backend.app.models.crm import CRMService
from backend.app.schemas.voice_onboarding import VoiceBusinessProfileRequest
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.voice_module_permission_service import VoiceModulePermissionService
from backend.app.services.plan_limits_service import PlanLimitsService
from backend.app.services.audit_log_service import AuditLogService
from backend.app.voice.module_actions import catalog_modules, actions_for_module

PROFILE_KEY = "voice_business"
INDUSTRY_SUGGESTIONS = ["Retail / e-commerce", "Automotive", "Hospitality", "Healthcare", "Beauty",
                        "Professional services", "Real estate", "Logistics", "Finance", "Education", "Other"]


def stored_business_profile(db, company_id):
    record = db.get(CompanyOnboarding, company_id, populate_existing=True)
    return dict((record.draft_payload or {}).get(PROFILE_KEY) or {}) if record else {}


class VoiceProfileConflict(ValueError):
    pass


class VoiceOnboardingService:
    def __init__(self, db):
        self.db = db

    def _owner(self, tenant, user_id):
        user = self.db.get(User, user_id)
        membership = self.db.scalar(select(CompanyMembership).where(
            CompanyMembership.company_id == tenant.company_id, CompanyMembership.user_id == user_id,
            CompanyMembership.is_active.is_(True)))
        if not user or not user.is_active or user.company_id != tenant.company_id or not membership or membership.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise PermissionError("Owner or administrator of this company required")

    def view(self, tenant):
        company = self.db.get(Company, tenant.company_id)
        if company is None:
            raise LookupError("Company unavailable")
        config = self.db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == tenant.company_id))
        saved = stored_business_profile(self.db, tenant.company_id)
        from backend.app.services.tenant_locale_service import get_profile
        locale = get_profile(self.db, tenant.company_id)
        values = {"business_name": config.business_name if config else company.name,
                  "industry": company.industry, "timezone": company.timezone,
                  "opening_hours": company.business_hours or (config.opening_hours if config else {}) or {},
                  "primary_locale": locale.primary_locale or company.preferred_language,
                  "secondary_locales": locale.secondary_locales, "contact_phone": company.phone,
                  "website": company.website or ""}
        values.update({k: v for k, v in saved.items() if k not in {"version", "expected_version"}})
        values["expected_version"] = saved.get("version", 0)
        if not saved and config:
            values["bookable_service_ids"] = [str(s["crm_service_id"]) for s in config.services or [] if s.get("crm_service_id")]
        profile = VoiceBusinessProfileRequest.model_validate(values)
        active = set(ModuleEntitlementService(self.db).get_active_modules(tenant))
        grants = VoiceModulePermissionService(self.db).granted_actions(tenant.company_id)
        if not saved:
            profile.allowed_actions = [f"{module}:{action}" for module, action in sorted(grants)]
        services = self.db.scalars(select(CRMService).where(CRMService.company_id == tenant.company_id,
            CRMService.is_active.is_(True)).order_by(CRMService.name)).all() if "crm" in active else []
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService
        context = CompanyIntelligenceService(self.db).get_profile(tenant.company_id)
        actions = [{"id": f"{module}:{action}", "module": module,
                    "granted": (module, action) in grants, "module_active": module in active}
                   for module in catalog_modules() for action in actions_for_module(module)]
        return {"profile": profile.model_dump(mode="json"), "industry_suggestions": INDUSTRY_SUGGESTIONS,
                "services": [{"id": str(s.id), "name": s.name, "duration_minutes": s.duration_minutes,
                              "price": s.price, "currency": s.currency} for s in services],
                "actions": actions, "active_modules": sorted(active), "context_version": context.context_version,
                "readiness": {"configuration_saved": bool(saved), "catalog_status": context.catalog_status,
                    "booking_configured": context.has_crm_booking,
                    "booking_authorized": context.has_crm_booking and ("crm", "create_appointment") in grants
                        and (not saved or "crm:create_appointment" in profile.allowed_actions),
                    "voice_enabled": bool(config and config.enabled), "telephone_verified": False}}

    def save(self, tenant, user_id, request):
        self._owner(tenant, user_id)
        if not ModuleEntitlementService(self.db).can_use_module(tenant, "voice"):
            raise PermissionError("Voice entitlement required")
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "voice-onboarding:" + str(tenant.company_id)})
        record = self.db.get(CompanyOnboarding, tenant.company_id, populate_existing=True)
        current = dict((record.draft_payload or {}).get(PROFILE_KEY) or {}) if record else {}
        if current.get("version", 0) != request.expected_version:
            raise VoiceProfileConflict("Business settings changed; reload before saving")
        limit = PlanLimitsService(self.db).limits_for(tenant.company_id).max_sites
        if limit is not None and len(request.locations) > limit:
            raise ValueError("Location count exceeds subscription allowance")
        active = set(ModuleEntitlementService(self.db).get_active_modules(tenant))
        if request.bookable_service_ids and "crm" not in active:
            raise PermissionError("CRM entitlement required for booking")
        ids = set(request.bookable_service_ids)
        services = self.db.scalars(select(CRMService).where(CRMService.company_id == tenant.company_id,
            CRMService.id.in_(ids), CRMService.is_active.is_(True))).all() if ids else []
        if {s.id for s in services} != ids:
            raise ValueError("Select active CRM services owned by this company")
        known = {f"{m}:{a}" for m in catalog_modules() for a in actions_for_module(m)}
        if not set(request.allowed_actions) <= known:
            raise ValueError("Unknown Voice capability")
        config = self.db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == tenant.company_id))
        if config is None:
            from backend.app.voice.service import new_voice_api_key, _api_key_hash, VoiceOrchestrator
            key = new_voice_api_key()
            config = VoiceBusinessConfig(company_id=tenant.company_id, business_name=request.business_name,
                voice_api_key_hash=_api_key_hash(key), voice_api_key_last4=key[-4:], enabled=False,
                greeting_message=VoiceOrchestrator.greeting_for(request.business_name, request.primary_locale))
            self.db.add(config)
        config.business_name, config.timezone_name = request.business_name, request.timezone
        config.opening_hours, config.preferred_language = request.opening_hours, request.primary_locale
        config.services = [{"name": s.name, "crm_service_id": str(s.id), "duration_minutes": s.duration_minutes,
                            "price": s.price, "currency": s.currency} for s in services]
        company = self.db.get(Company, tenant.company_id)
        company.industry, company.timezone = request.industry, request.timezone
        company.business_hours, company.phone, company.website = request.opening_hours, request.contact_phone, request.website or None
        from backend.app.services.tenant_locale_service import upsert_profile
        from backend.app.services.tenant_locale_service import get_profile
        old_locale = get_profile(self.db, tenant.company_id)
        upsert_profile(self.db, tenant.company_id, primary_locale=request.primary_locale,
                       secondary_locales=request.secondary_locales, voice_by_locale=old_locale.voice_by_locale)
        if record is None:
            record = CompanyOnboarding(company_id=tenant.company_id)
            self.db.add(record)
        payload = request.model_dump(mode="json", exclude={"expected_version"})
        payload["version"] = request.expected_version + 1
        record.draft_payload = {**(record.draft_payload or {}), PROFILE_KEY: payload}
        AuditLogService(self.db).record(actor_user_id=user_id, action="voice_business_profile_updated",
            target_type="company", target_id=str(tenant.company_id), company_id=tenant.company_id,
            metadata={"version": payload["version"], "service_count": len(services)}, commit=False)
        self.db.commit()
        return self.view(tenant)
