"""Typed, tenant-scoped, RBAC-enforced voice & Central AI intelligence tools.

Reuses existing Avenqo services (`ModuleEntitlementService`, `CompanyIntelligenceService`,
`semantic_search_products`, `AccountingIntelligenceService`) — zero duplicate business logic,
zero hardcoded conversational scripts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.core.permissions import (
    is_executive_role,
    normalize_role,
    permissions_for,
    resolve_verified_staff_role,
)
from backend.app.models.commerce_connection import CommerceConnection
from backend.app.models.company import Company
from backend.app.models.user import User
from backend.app.services.company_intelligence_service import (
    CompanyIntelligenceService,
    classify_connector_freshness,
)
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.semantic_product_search import (
    semantic_search_products,
    summarize_catalog_freshness,
)
from backend.app.voice.caller_scope import is_public_voice_caller


_VOICE_IDENTITY_AGENT_IDS = frozenset({
    "voice",
    "cross_agent",
    "central",
})
_VOICE_RETAIL_AGENT_IDS = frozenset({
    "voice",
    "retail",
    "cross_agent",
    "central",
})

# Concise functional descriptions used by `list_enabled_modules` so the generative LLM
# can accurately explain what each subscribed module enables for any business.
MODULE_CAPABILITY_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "retail": {
        "name": "Retail Intelligence",
        "purpose": "Catalogue produits, prix, suivi d'inventaire, ventes e-commerce (Shopify/WooCommerce), tendances, prévisions de demande et détection d'anomalies.",
    },
    "crm": {
        "name": "CRM AI",
        "purpose": "Gestion des clients, prospects, prises de rendez-vous, disponibilités calendrier, historique client et relances commerciales.",
    },
    "accounting": {
        "name": "Accounting AI",
        "purpose": "Suivi des factures clients/fournisseurs, dépenses mensuelles, trésorerie, marges financières et rapprochement comptable.",
    },
    "voice": {
        "name": "Voice AI",
        "purpose": "Réceptionniste et assistant téléphonique vocal temps réel multilingue, authentification sécurisée par NIP et orchestration des modules autorisés.",
    },
    "hr": {
        "name": "HR AI",
        "purpose": "Gestion d'équipe, organisation interne, tâches opérationnelles et accompagnement des employés.",
    },
    "trading": {
        "name": "Trading AI",
        "purpose": "Suivi de cotations d'actifs, signaux prédictifs et analyse de risque de portefeuille.",
    },
    "marketing": {
        "name": "Marketing AI",
        "purpose": "Préparation de campagnes marketing, segmentation d'audience et optimisation de l'acquisition client.",
    },
    "ocr": {
        "name": "OCR & Documents AI",
        "purpose": "Numérisation, extraction et recherche intelligente dans les reçus, factures et documents d'entreprise.",
    },
    "legal": {
        "name": "Legal AI",
        "purpose": "Analyse et recherche de contrats, clauses et documents juridiques.",
    },
    "workflow": {
        "name": "Workflow Automation",
        "purpose": "Automatisation de processus métier et déclencheurs entre modules Avenqo.",
    },
}


class EmptyVoiceIntelArgs(ToolArguments):
    pass


class SearchProductsArgs(ToolArguments):
    query: str | None = Field(
        default=None,
        description=(
            "Product name, product type, or descriptive search query (e.g. 'casque de snowboard', "
            "'headphones', 'snowboard', 'gants', or empty/'all' to browse catalog)."
        ),
    )
    category: str | None = Field(
        default=None,
        description="Optional category filter (e.g. 'accessoire', 'planche', 'electronics').",
    )
    filter_mode: str | None = Field(
        default=None,
        description="Optional filter/sort mode: 'in_stock' (verified live stock only), 'promote' (discounted/compare-at items first), or 'all'.",
    )
    limit: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Maximum number of products to return.",
    )


class ProductMarginArgs(ToolArguments):
    product_query: str | None = Field(
        default=None,
        description="Optional product name or category to inspect margins for.",
    )
    limit: int = Field(default=5, ge=1, le=20)


def _safe_float(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace("$", "").replace("€", "").replace("£", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


class GetMyIdentityTool(AITool):
    name = "get_my_identity"
    description = (
        "Return the authenticated caller's server-verified identity, canonical role "
        "(e.g. owner, admin, manager, user), executive privilege status, company name, "
        "and active permission scope. Never available to unauthenticated public callers."
    )
    input_schema = EmptyVoiceIntelArgs
    required_permissions = ("ai:use",)
    read_only = True
    mutates = False
    agent_ids = _VOICE_IDENTITY_AGENT_IDS

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: EmptyVoiceIntelArgs) -> ToolResult:
        if is_public_voice_caller(context.permissions) or context.user_id is None:
            return ToolResult(
                success=False,
                error="authentication_required",
                data={"authenticated": False, "message": "PIN authentication is required to verify employee identity."},
            )
        user = self._session.get(User, context.user_id)
        company = self._session.get(Company, context.tenant.company_id)
        if user is None or not user.is_active or user.company_id != context.tenant.company_id:
            return ToolResult(success=False, error="unauthorized_user")

        verified_role = resolve_verified_staff_role(
            self._session, context.tenant.company_id, user.id, fallback_role=user.role
        )
        effective_perms = sorted(set(permissions_for(verified_role)) & set(context.permissions or permissions_for(verified_role)))
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.first_name or "Collaborateur"
        return ToolResult(
            success=True,
            data={
                "authenticated": True,
                "user_id": str(user.id),
                "full_name": full_name,
                "first_name": user.first_name or "",
                "canonical_role": verified_role,
                "is_executive_role": is_executive_role(verified_role),
                "job_title": user.job_title or "",
                "company_name": (company.name.replace("_", " ") if company else ""),
                "permissions_count": len(effective_perms),
                "can_view_margins": is_executive_role(verified_role),
            },
            source_refs=("users", "company_memberships", "companies"),
        )


class ListEnabledModulesTool(AITool):
    name = "list_enabled_modules"
    description = (
        "Return the tenant's truly active/subscribed Avenqo modules, subscription plan, "
        "and concise descriptions of what each enabled module enables the company to do. "
        "Authenticated staff only."
    )
    input_schema = EmptyVoiceIntelArgs
    required_permissions = ("ai:use",)
    read_only = True
    mutates = False
    agent_ids = _VOICE_IDENTITY_AGENT_IDS

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: EmptyVoiceIntelArgs) -> ToolResult:
        if is_public_voice_caller(context.permissions) or context.user_id is None:
            return ToolResult(
                success=False,
                error="authentication_required",
                data={"authenticated": False},
            )
        summary = ModuleEntitlementService(self._session).summary(context.tenant)
        company = self._session.get(Company, context.tenant.company_id)
        active_items: list[dict[str, str]] = []
        for mod in summary.modules:
            if not mod.active:
                continue
            info = MODULE_CAPABILITY_DESCRIPTIONS.get(mod.key, {})
            active_items.append({
                "key": mod.key,
                "display_name": mod.display_name or info.get("name") or mod.key,
                "purpose": info.get("purpose", "Module Avenqo actif pour votre entreprise."),
            })
        return ToolResult(
            success=True,
            data={
                "company_name": (company.name.replace("_", " ") if company else ""),
                "industry": (company.industry if company else ""),
                "plan_code": summary.plan_code,
                "subscription_status": summary.subscription_status,
                "enabled_modules": active_items,
                "enabled_module_keys": list(summary.active_modules),
                "module_limit": summary.module_limit,
                "remaining_module_slots": summary.remaining_module_slots,
            },
            source_refs=("company_modules", "billing_accounts"),
        )


class SearchProductsTool(AITool):
    name = "search_products"
    description = (
        "Semantically search the tenant's real product catalog by product name, type, usage, "
        "category, or promotional filter ('in_stock', 'promote', 'all'). Returns explicit "
        "status ('found', 'ambiguous', 'not_found', 'browse_catalog') with relevance reasons "
        "and a single concise freshness summary. Never substitutes unrelated products when not found."
    )
    input_schema = SearchProductsArgs
    required_permissions = ("ai:use",)
    read_only = True
    mutates = False
    agent_ids = _VOICE_RETAIL_AGENT_IDS

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: SearchProductsArgs) -> ToolResult:
        profile = CompanyIntelligenceService(self._session).get_profile(context.tenant.company_id)
        if not profile.has_retail_commerce:
            return ToolResult(
                success=True,
                data={
                    "available": False,
                    "status": "retail_module_inactive",
                    "message": "Retail catalog module is not enabled for this company.",
                },
            )

        public_caller = is_public_voice_caller(context.permissions)
        verified_role = (
            ""
            if public_caller
            else resolve_verified_staff_role(self._session, context.tenant.company_id, context.user_id)
        )
        can_see_margins = (not public_caller) and is_executive_role(verified_role)

        products = [p for p in (profile.public_products or ()) if isinstance(p, dict)]
        fmode = (arguments.filter_mode or "").strip().lower()
        if fmode == "in_stock":
            products = [
                p for p in products
                if p.get("is_live_stock") is True
                and (p.get("in_stock") is True or p.get("stock_availability") == "IN_STOCK")
            ]
            if not products:
                return ToolResult(
                    success=True,
                    data={
                        "available": True,
                        "status": "no_live_stock_confirmed",
                        "found": False,
                        "matches": [],
                        "freshness_summary": summarize_catalog_freshness(list(profile.public_products or ())),
                        "message": "No products currently have verified real-time stock because inventory sync is not live.",
                    },
                    source_refs=("normalized_commerce_records",),
                )
        elif fmode == "promote":
            def _promo_key(p: dict[str, Any]) -> tuple[int, float, float]:
                pv = _safe_float(p.get("price")) or 0.0
                cv = _safe_float(p.get("compare_at_price")) or 0.0
                if cv > pv > 0:
                    return (1, round((cv - pv) / cv, 4), round(cv - pv, 2))
                return (0, 0.0, pv)
            products = sorted(products, key=_promo_key, reverse=True)

        sem = semantic_search_products(
            products,
            arguments.query,
            category=arguments.category,
            limit=arguments.limit,
        )

        projected_matches: list[dict[str, Any]] = []
        for match in sem.matches:
            row = match.product
            item: dict[str, Any] = {
                "name": row.get("name"),
                "category": row.get("category") or "",
                "price": row.get("price"),
                "compare_at_price": row.get("compare_at_price"),
                "currency": row.get("currency") or profile.currency_code,
                "is_live_stock": bool(row.get("is_live_stock")),
                "stock_availability": row.get("stock_availability") or "UNKNOWN",
                "in_stock": row.get("in_stock"),
                "inventory_count": row.get("inventory_count") if row.get("is_live_stock") else None,
                "match_score": match.score,
                "match_reason": match.match_reason,
                "product_domain": match.product_domain,
            }
            if can_see_margins and (
                row.get("unit_cost") is not None
                or row.get("profit_margin_amount") is not None
                or row.get("profit_margin_pct") is not None
            ):
                item["unit_cost"] = row.get("unit_cost")
                item["profit_margin_amount"] = row.get("profit_margin_amount")
                item["profit_margin_pct"] = row.get("profit_margin_pct")
            projected_matches.append(item)

        return ToolResult(
            success=True,
            data={
                "available": True,
                "status": sem.status,
                "found": sem.found,
                "query": sem.query,
                "filter_mode": fmode or "all",
                "total_catalog_products": len(profile.public_products or ()),
                "matches": projected_matches,
                "related_other_category": list(sem.related_other_category),
                "ambiguity_note": sem.ambiguity_note,
                "not_found_reason": sem.not_found_reason,
                "freshness_summary": sem.freshness_summary,
                "spoken_style_hint": (
                    "State prices cleanly without repeating stock disclaimers on every item. "
                    "Mention live stock uncertainty at most ONCE briefly if the caller asked about stock/availability."
                ),
            },
            source_refs=("normalized_commerce_records",),
        )


class GetProductMarginsTool(AITool):
    name = "get_product_margins"
    description = (
        "Inspect product profitability and margin data for authenticated company leadership "
        "(owner, admin, manager). Strictly enforces server-side RBAC from CompanyMembership; "
        "never substitutes selling price for profitability when unit cost or margin data is absent."
    )
    input_schema = ProductMarginArgs
    required_permissions = ("ai:use",)
    read_only = True
    mutates = False
    agent_ids = _VOICE_RETAIL_AGENT_IDS

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: ProductMarginArgs) -> ToolResult:
        if is_public_voice_caller(context.permissions) or context.user_id is None:
            return ToolResult(
                success=False,
                error="authentication_required",
                data={"authorized": False, "reason": "PIN authentication is required for profitability data."},
            )
        verified_role = resolve_verified_staff_role(
            self._session, context.tenant.company_id, context.user_id
        )
        if not is_executive_role(verified_role):
            return ToolResult(
                success=False,
                error="executive_role_required",
                data={
                    "authorized": False,
                    "verified_role": verified_role,
                    "reason": "Profitability and margin data are restricted to company leadership (owner, admin, manager).",
                },
            )

        profile = CompanyIntelligenceService(self._session).get_profile(context.tenant.company_id)
        products = [p for p in (profile.public_products or ()) if isinstance(p, dict)]
        if arguments.product_query:
            sem = semantic_search_products(products, arguments.product_query, limit=arguments.limit)
            products = [m.product for m in sem.matches] if sem.matches else []

        margin_rows: list[dict[str, Any]] = []
        promo_rows: list[dict[str, Any]] = []
        for p in products:
            price = _safe_float(p.get("price"))
            cmp_price = _safe_float(p.get("compare_at_price"))
            if price is not None and cmp_price is not None and cmp_price > price > 0:
                promo_rows.append({
                    "name": p.get("name"),
                    "price": price,
                    "compare_at_price": cmp_price,
                    "discount_pct": round(((cmp_price - price) / cmp_price) * 100.0, 1),
                    "currency": p.get("currency") or profile.currency_code,
                })
            unit_cost = _safe_float(p.get("unit_cost"))
            margin_amt = _safe_float(p.get("profit_margin_amount"))
            margin_pct = _safe_float(p.get("profit_margin_pct"))
            if margin_amt is None and unit_cost is not None and price is not None:
                margin_amt = round(price - unit_cost, 2)
            if margin_pct is None and margin_amt is not None and price is not None and price > 0:
                margin_pct = round((margin_amt / price) * 100.0, 2)
            if margin_amt is not None or margin_pct is not None:
                margin_rows.append({
                    "name": p.get("name"),
                    "price": price,
                    "unit_cost": unit_cost,
                    "profit_margin_amount": margin_amt,
                    "profit_margin_pct": margin_pct,
                    "currency": p.get("currency") or profile.currency_code,
                })

        margin_rows.sort(
            key=lambda r: (r.get("profit_margin_amount") or 0.0, r.get("profit_margin_pct") or 0.0),
            reverse=True,
        )
        promo_rows.sort(key=lambda r: r.get("discount_pct") or 0.0, reverse=True)

        if not margin_rows:
            return ToolResult(
                success=True,
                data={
                    "authorized": True,
                    "verified_role": verified_role,
                    "margin_data_available": False,
                    "products_with_margins": [],
                    "promotional_opportunities": promo_rows[: arguments.limit],
                    "reason": (
                        "No unit cost or margin data is stored in the synced catalog yet; "
                        "selling prices alone cannot determine profitability."
                    ),
                },
                source_refs=("normalized_commerce_records",),
            )

        return ToolResult(
            success=True,
            data={
                "authorized": True,
                "verified_role": verified_role,
                "margin_data_available": True,
                "products_with_margins": margin_rows[: arguments.limit],
                "promotional_opportunities": promo_rows[: arguments.limit],
            },
            source_refs=("normalized_commerce_records",),
        )


class GetInventoryFreshnessTool(AITool):
    name = "get_inventory_freshness"
    description = (
        "Check whether the tenant's e-commerce connectors have live/recent inventory sync "
        "or stale/unverified sync status. Authenticated staff only."
    )
    input_schema = EmptyVoiceIntelArgs
    required_permissions = ("ai:use",)
    read_only = True
    mutates = False
    agent_ids = _VOICE_RETAIL_AGENT_IDS

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: EmptyVoiceIntelArgs) -> ToolResult:
        if is_public_voice_caller(context.permissions) or context.user_id is None:
            return ToolResult(success=False, error="authentication_required")
        profile = CompanyIntelligenceService(self._session).get_profile(context.tenant.company_id)
        if not profile.has_retail_commerce:
            return ToolResult(
                success=True,
                data={"retail_enabled": False, "is_live_stock_available": False},
            )
        conns = list(
            self._session.scalars(
                select(CommerceConnection).where(
                    CommerceConnection.company_id == context.tenant.company_id
                )
            ).all()
        )
        now = datetime.now(timezone.utc)
        details = []
        any_fresh = False
        for c in conns:
            fresh = classify_connector_freshness(c, now=now)
            if fresh == "FRESH":
                any_fresh = True
            details.append({
                "provider": c.provider,
                "display_name": c.display_name or c.provider,
                "status": c.status,
                "freshness_status": fresh,
                "last_successful_sync": c.last_successful_sync.isoformat() if c.last_successful_sync else None,
            })
        return ToolResult(
            success=True,
            data={
                "retail_enabled": True,
                "is_live_stock_available": any_fresh,
                "connectors": details,
                "catalog_freshness": summarize_catalog_freshness(list(profile.public_products or ())),
            },
            source_refs=("commerce_connections",),
        )


__all__ = [
    "GetInventoryFreshnessTool",
    "GetMyIdentityTool",
    "GetProductMarginsTool",
    "ListEnabledModulesTool",
    "MODULE_CAPABILITY_DESCRIPTIONS",
    "SearchProductsTool",
]
