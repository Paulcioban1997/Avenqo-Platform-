"""Live company grounding. No defaults that invent offerings or elevate callers."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.models import Company, VoiceBusinessConfig, CommerceConnection, Dataset
from backend.app.models.crm import CRMService, CRMCalendarConnection, CRMEmployee
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

BOOKING_TOOLS = frozenset({"check_availability", "list_available_slots", "create_appointment", "book_appointment"})

class CompanyOfferingUnavailable(ValueError):
    pass

@dataclass(frozen=True, slots=True)
class CompanyIntelligenceProfile:
    company_id: UUID
    company_name: str
    business_name: str
    industry: str
    timezone: str
    currency_code: str
    preferred_language: str
    opening_hours: dict
    active_modules: tuple[str, ...]
    configured_crm_services: tuple[dict, ...]
    has_crm_booking: bool
    has_retail_commerce: bool
    connected_integrations: tuple[dict, ...]
    has_google_calendar: bool
    catalog_status: str
    available_datasets: tuple[dict, ...]
    business_configuration: dict
    context_version: str
    calendar_resources: tuple[dict, ...]
    public_products: tuple[dict, ...] = ()
    phone: str | None = None
    website: str | None = None
    voice_display_name: str | None = None
    voice_pronunciation: str | None = None
    has_online_store: bool = False
    online_store_url: str | None = None
    online_store_name: str | None = None
    online_ordering_available: bool = False
    phone_ordering_policy: str | None = None

    def as_context(self, *, public: bool = False) -> dict:
        data = asdict(self)
        data["company_id"] = str(self.company_id)
        data["voice_display_name"] = self.voice_display_name or self.business_name.replace("_", " ")
        data["voice_pronunciation"] = self.voice_pronunciation or data["voice_display_name"]
        if public:
            # Connection/dataset identities and operational state are private.
            data.pop("connected_integrations", None)
            data.pop("available_datasets", None)
            data.pop("calendar_resources", None)
        return data

class CompanyIntelligenceService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_profile(self, company_id: UUID) -> CompanyIntelligenceProfile:
        from backend.app.core.tenant_execution import peek_tenant_execution, TenantExecutionError
        execution = peek_tenant_execution()
        if execution is not None and execution.company_id != company_id:
            raise TenantExecutionError("Company context cannot cross the bound tenant")
        company = self._session.get(Company, company_id, populate_existing=True)
        if company is None:
            raise CompanyOfferingUnavailable("Company context unavailable")
        config = self._session.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id).execution_options(populate_existing=True))
        from backend.app.services.voice_onboarding_service import stored_business_profile
        business = stored_business_profile(self._session, company_id)
        active = tuple(ModuleEntitlementService(self._session).get_active_modules(TenantContext(company_id)))
        services = self._session.scalars(
            select(CRMService).where(
                CRMService.company_id == company_id,
                CRMService.is_active.is_(True),
                CRMService.is_approved_by_owner.is_(True),
                CRMService.is_published.is_(True),
            ).order_by(CRMService.name, CRMService.id).execution_options(populate_existing=True)
        ).all() if "crm" in active else []
        # CRM is the source of service IDs/durations/prices. A non-empty Voice
        # catalog is an explicit allowlist, never authority to create services.
        configured = [s for s in (config.services or []) if isinstance(s, dict) and s.get("name")] if config else []
        status = "configured" if services else "not_configured"
        if configured:
            names = {str(s["name"]).strip().casefold() for s in configured}
            ids = {str(s.get("crm_service_id") or s.get("id")) for s in configured if s.get("crm_service_id") or s.get("id")}
            services = [s for s in services if str(s.id) in ids or s.name.strip().casefold() in names]
            if not services:
                status = "voice_crm_catalog_mismatch"
        if business and business.get("bookable_service_ids"):
            selected = set(business.get("bookable_service_ids", []))
            services = [s for s in services if str(s.id) in selected]
            if not services:
                status = "booking_not_selected"
        offerings = tuple({"id": str(s.id), "crm_service_id": str(s.id), "name": s.name, "duration_minutes": s.duration_minutes, "price": s.price, "currency": s.currency} for s in services)
        connections = self._session.scalars(select(CommerceConnection).where(CommerceConnection.company_id == company_id)).all()
        calendar = self._session.scalar(select(CRMCalendarConnection).where(CRMCalendarConnection.company_id == company_id))
        datasets = self._session.scalars(select(Dataset).where(Dataset.company_id == company_id).order_by(Dataset.id)).all()
        connected_calendar = bool(calendar and calendar.sync_status == "connected")
        resources = self._session.scalars(select(CRMEmployee).where(CRMEmployee.company_id == company_id,
            CRMEmployee.is_active.is_(True)).limit(100)).all() if "crm" in active else []

        products_list: list[dict] = []
        if "retail" in active:
            try:
                from backend.app.models.commerce_connection import NormalizedCommerceRecord
                records = self._session.scalars(
                    select(NormalizedCommerceRecord).where(
                        NormalizedCommerceRecord.company_id == company_id,
                        NormalizedCommerceRecord.entity_type.in_(["products", "product"]),
                        NormalizedCommerceRecord.deleted.is_(False),
                    ).order_by(NormalizedCommerceRecord.source_updated_at.desc().nullslast()).limit(50)
                ).all()
                for r in records:
                    pdata = r.normalized_data or {}
                    status = str(pdata.get("status") or pdata.get("stock_status") or "").lower().strip()
                    if status in ("archived", "draft", "trash"):
                        continue
                    pname = pdata.get("product_name") or pdata.get("name") or pdata.get("title")
                    if not pname:
                        continue
                    variants = pdata.get("variants") or []
                    price = pdata.get("unit_price")
                    if price is None:
                        price = pdata.get("price") if pdata.get("price") is not None else pdata.get("regular_price")
                    if price is None and isinstance(variants, list) and variants:
                        price = variants[0].get("unit_price") or variants[0].get("price")

                    inventory = pdata.get("inventory_level")
                    if inventory is None:
                        inventory = pdata.get("stock_quantity")
                    if inventory is None and isinstance(variants, list) and variants:
                        inventory = sum(v.get("inventory_level", 0) for v in variants if isinstance(v.get("inventory_level"), (int, float)))
                    inventory_count = int(inventory) if isinstance(inventory, (int, float)) else 0

                    in_stock = pdata.get("in_stock")
                    if in_stock is None:
                        in_stock = inventory_count > 0 or status == "instock"

                    products_list.append({
                        "id": str(r.id),
                        "name": str(pname).strip(),
                        "category": pdata.get("product_category") or pdata.get("category") or "",
                        "price": str(price) if isinstance(price, str) else (float(price) if isinstance(price, (int, float)) else None),
                        "currency": company.currency_code,
                        "in_stock": bool(in_stock),
                        "inventory_count": inventory_count,
                        "description": pdata.get("description") or pdata.get("body_html") or "",
                    })
            except Exception:
                products_list = []

        voice_spoken_name = config.effective_voice_name if config else company.name.replace("_", " ")
        voice_pronun = getattr(config, "custom_pronunciation", None) if config else None

        online_store_conn = next(
            (c for c in connections if c.provider in ("shopify", "woocommerce") and str(c.status).upper() in ("READY", "SYNCING", "ACTIVE")),
            None
        )
        has_store = online_store_conn is not None
        store_url = None
        store_name = None
        if online_store_conn:
            store_name = online_store_conn.display_name or (company.name.replace("_", " "))
            sync_cur = online_store_conn.sync_cursor or {}
            shop_domain = sync_cur.get("shop", {}).get("domain") or online_store_conn.external_account_id
            if company.website and "http" in company.website:
                store_url = company.website
            elif shop_domain:
                store_url = f"https://{str(shop_domain).removeprefix('https://').removeprefix('http://')}"
            else:
                store_url = company.website
        ordering_policy = (
            f"Les clients peuvent consulter notre catalogue et passer commande en ligne sur notre boutique officielle : {store_url}. "
            "Pour des raisons de conformité et de sécurité des paiements, nous ne prenons pas de coordonnées bancaires par téléphone."
            if has_store and store_url else
            "La commande en ligne est en cours de configuration. Pour le moment, les clients sont invités à nous contacter directement ou à se rendre en boutique."
        )

        signature = {"business": business, "services": offerings, "modules": active,
                     "name": company.name, "industry": company.industry, "timezone": company.timezone,
                     "hours": company.business_hours, "voice_services": config.services if config else [],
                     "datasets": [(str(d.id), str(d.status)) for d in datasets], "calendar": connected_calendar,
                     "products": products_list, "phone": company.phone, "website": company.website,
                     "voice_display_name": voice_spoken_name, "voice_pronunciation": voice_pronun,
                     "online_store_url": store_url}
        signature["resources"] = [(str(r.id), r.name, r.working_hours) for r in resources]
        version = hashlib.sha256(json.dumps(signature, sort_keys=True, default=str).encode()).hexdigest()[:24]
        return CompanyIntelligenceProfile(
            company_id=company_id, company_name=company.name,
            business_name=(config.business_name if config else None) or company.name,
            industry=company.industry or "unspecified", timezone=company.timezone,
            currency_code=company.currency_code, preferred_language=(config.preferred_language if config else None) or company.preferred_language,
            opening_hours=company.business_hours or (config.opening_hours if config else None) or {}, active_modules=active,
            configured_crm_services=offerings, has_crm_booking=bool("crm" in active and offerings),
            has_retail_commerce="retail" in active,
            connected_integrations=tuple({"provider": c.provider, "status": c.status} for c in connections),
            has_google_calendar=connected_calendar, catalog_status=status,
            available_datasets=tuple({"id": str(d.id), "name": d.name, "status": str(d.status)} for d in datasets),
            business_configuration={k: v for k, v in business.items() if k not in {"allowed_actions", "expected_version"}},
            context_version=version,
            calendar_resources=tuple({"id": str(r.id), "name": r.name, "working_hours": r.working_hours} for r in resources),
            public_products=tuple(products_list),
            phone=company.phone or (config.transfer_phone if config else None),
            website=company.website,
            voice_display_name=voice_spoken_name,
            voice_pronunciation=voice_pronun or voice_spoken_name,
            has_online_store=has_store,
            online_store_url=store_url,
            online_store_name=store_name,
            online_ordering_available=has_store,
            phone_ordering_policy=ordering_policy,
        )

    def require_service(self, company_id: UUID, *, service_id=None, service_name=None) -> dict:
        profile = self.get_profile(company_id)
        if not profile.has_crm_booking:
            raise CompanyOfferingUnavailable("No verified bookable service is configured for this company")
        matches = [s for s in profile.configured_crm_services if
                   (service_id is not None and s["id"] == str(service_id)) or
                   (service_id is None and service_name is not None and s["name"].strip().casefold() == str(service_name).strip().casefold())]
        if not matches and service_name and service_id is None:
            norm_name = str(service_name).strip().casefold()
            matches = [s for s in profile.configured_crm_services if norm_name in s["name"].strip().casefold() or s["name"].strip().casefold() in norm_name]
            if not matches:
                # Fallback: check for store pickup / product reservation keywords
                pickup_kw = ("cueillette", "ramassage", "retrait", "reserve", "reserver", "reservation", "produit", "magasin", "boutique", "pickup", "pick up", "snowboard")
                if any(k in norm_name for k in pickup_kw):
                    pickup_matches = [
                        s for s in profile.configured_crm_services
                        if any(k in s["name"].lower() for k in ("cueillette", "ramassage", "retrait", "magasin", "reservation", "boutique"))
                    ]
                    if len(pickup_matches) == 1:
                        matches = pickup_matches
        if service_id is None and not service_name and len(profile.configured_crm_services) == 1:
            matches = list(profile.configured_crm_services)
        if len(matches) != 1:
            avail = ", ".join(f"'{s['name']}'" for s in profile.configured_crm_services) if profile.configured_crm_services else "aucun"
            raise CompanyOfferingUnavailable(f"Veuillez sélectionner un service actif proposé par l'entreprise. Services disponibles : {avail}")
        return matches[0]
