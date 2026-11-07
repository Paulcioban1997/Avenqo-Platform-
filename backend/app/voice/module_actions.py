"""Voice module/action catalog.

Activated modules never imply Voice tools. Grants are explicit enums mapped to
registered tool names. Unknown actions or unmapped tools cannot be invented.
"""

from __future__ import annotations

from enum import StrEnum

from modules.registry import BUSINESS_MODULE_REGISTRY


class VoiceModuleAction(StrEnum):
    CRM_READ_AVAILABILITY = "crm:read_availability"
    CRM_LIST_SLOTS = "crm:list_slots"
    CRM_CREATE_APPOINTMENT = "crm:create_appointment"
    CRM_UPDATE_APPOINTMENT = "crm:update_appointment"
    CRM_CANCEL_APPOINTMENT = "crm:cancel_appointment"
    CRM_READ_CLIENT_SELF = "crm:read_client_self"
    CRM_READ_CRM_METRICS = "crm:read_crm_metrics"
    RETAIL_READ_SALES_SUMMARY = "retail:read_sales_summary"
    RETAIL_READ_PRODUCTS = "retail:read_products"
    RETAIL_READ_INVENTORY = "retail:read_inventory"
    ACCOUNTING_READ_UNPAID_INVOICES = "accounting:read_unpaid_invoices"
    ACCOUNTING_READ_CASHFLOW = "accounting:read_cashflow"
    OCR_READ_DOCUMENTS = "ocr:read_documents"
    MARKETING_READ = "marketing:read"
    APPOINTMENTS_READ = "appointments:read"
    HR_READ = "hr:read"
    MEDIA_READ = "media:read"
    LEGAL_READ = "legal:read"
    WORKFLOW_READ = "workflow:read"
    AI_AGENTS_READ = "ai_agents:read"
    CROSS_AGENT_READ_BUSINESS_HEALTH = "cross_agent:read_business_health"


# Voice-native tools are the agent itself (greeting, PIN, transfer). They do not
# read other modules and do not require a VoiceModulePermission row.
VOICE_NATIVE_TOOLS: frozenset[str] = frozenset({
    "get_business_info",
    "take_message",
    "transfer_to_human",
    "request_caller_verification",
    "request_pin_authentication",
    "verify_caller",
})

VOICE_WRITE_TOOLS: frozenset[str] = frozenset({
    "create_appointment",
    "update_appointment",
    "cancel_appointment",
    "book_appointment",
    "reschedule_appointment",
})

# Orchestrator aliases used by Retell, mapped onto the same CRM actions.
VOICE_TOOL_ALIASES: dict[str, str] = {
    "book_appointment": "create_appointment",
    "reschedule_appointment": "update_appointment",
}

# action_code → registered Central/Retell tool names. Empty means the module
# may be granted but Voice still cannot invent tools for it.
VOICE_ACTION_TOOLS: dict[str, dict[str, frozenset[str]]] = {
    "crm": {
        "read_availability": frozenset({"check_availability"}),
        "list_slots": frozenset({"list_available_slots"}),
        "create_appointment": frozenset({"create_appointment", "book_appointment"}),
        "update_appointment": frozenset({"update_appointment", "reschedule_appointment"}),
        "cancel_appointment": frozenset({"cancel_appointment"}),
        "read_client_self": frozenset({
            "get_client",
            "search_clients",
            "get_client_history",
            "search_appointments",
        }),
        "read_crm_metrics": frozenset({
            "get_crm_metrics",
            "get_crm_overview",
            "get_leads_to_contact",
            "get_ranked_leads",
            "get_high_risk_customers",
            "get_top_revenue_deals",
            "get_follow_up_recommendation",
        }),
    },
    "retail": {
        "read_sales_summary": frozenset({
            "get_sales_summary",
            "get_sales_trend",
            "get_sales_comparison",
            "get_business_overview",
            "get_customer_summary",
            "get_customer_segments",
            "get_churn_risk",
            "get_segment_insights",
            "get_demand_forecast",
            "get_sales_forecast",
            "get_anomalies",
            "get_prediction_summary",
        }),
        "read_products": frozenset({"get_top_products", "get_product_detail"}),
        "read_inventory": frozenset({"get_inventory_summary"}),
    },
    "accounting": {
        "read_unpaid_invoices": frozenset({"get_unpaid_invoices"}),
        "read_cashflow": frozenset({
            "get_cash_flow_forecast",
            "get_financial_overview",
            "get_monthly_expenses",
            "get_profit_margin",
            "get_expense_anomalies",
        }),
    },
    "ocr": {"read_documents": frozenset()},
    "marketing": {"read": frozenset()},
    "appointments": {"read": frozenset()},
    "hr": {"read": frozenset()},
    "media": {"read": frozenset()},
    "legal": {"read": frozenset()},
    "workflow": {"read": frozenset()},
    "ai_agents": {"read": frozenset()},
    "cross_agent": {"read_business_health": frozenset({"get_cross_agent_business_health"})},
}

_TOOL_TO_ACTION: dict[str, tuple[str, str]] = {}
for _module, _actions in VOICE_ACTION_TOOLS.items():
    for _action, _tools in _actions.items():
        for _tool in _tools:
            _TOOL_TO_ACTION[_tool] = (_module, _action)


def known_action(module_code: str, action_code: str) -> bool:
    return action_code in VOICE_ACTION_TOOLS.get(module_code, {})


def catalog_modules() -> tuple[str, ...]:
    registry = [item.key for item in BUSINESS_MODULE_REGISTRY if item.key != "voice"]
    extra = [code for code in VOICE_ACTION_TOOLS if code not in registry and code != "voice"]
    return tuple(dict.fromkeys([*registry, *extra]))


def actions_for_module(module_code: str) -> tuple[str, ...]:
    return tuple(VOICE_ACTION_TOOLS.get(module_code, {}))


def tools_for_action(module_code: str, action_code: str) -> frozenset[str]:
    return VOICE_ACTION_TOOLS.get(module_code, {}).get(action_code, frozenset())


def tools_for_grants(grants: set[tuple[str, str]]) -> frozenset[str]:
    names: set[str] = set()
    for module_code, action_code in grants:
        names.update(tools_for_action(module_code, action_code))
    return frozenset(names)


def action_for_tool(tool_name: str) -> tuple[str, str] | None:
    canonical = VOICE_TOOL_ALIASES.get(tool_name, tool_name)
    return _TOOL_TO_ACTION.get(tool_name) or _TOOL_TO_ACTION.get(canonical)


def is_voice_native_tool(tool_name: str) -> bool:
    return tool_name in VOICE_NATIVE_TOOLS


def voice_agent_language(db, config) -> str:
    """Prefer TenantLocaleProfile when importable (#38); else VoiceBusinessConfig."""
    from backend.app.services.tenant_locale_service import get_stored_profile

    profile = get_stored_profile(db, config.company_id)
    if profile is not None:
        return profile.primary_locale
    # A configured legacy Voice language remains explicit; no automatic locale.
    from backend.app.services.tenant_locale_service import catalog_code_or_none
    locale = catalog_code_or_none(getattr(config, "preferred_language", None))
    if locale is None:
        raise ValueError("Voice primary language must be configured")
    return locale


def company_call_language_session(db, config, call):
    """Use only the server-side tenant profile; never trust call metadata grants."""
    from backend.app.services.tenant_locale_service import get_stored_profile
    from backend.app.voice.language_resolver import CallLanguageSession, to_bcp47

    if call.company_id != config.company_id:
        raise PermissionError("Voice call belongs to another tenant")
    primary = voice_agent_language(db, config)
    profile = get_stored_profile(db, config.company_id)
    allowed = tuple(to_bcp47(code) for code in (
        [primary, *(profile.secondary_locales or [])] if profile else [primary]
    ))
    saved = (call.source_context or {}).get("call_language_session") or {}
    previous = saved.get("active_locale") if isinstance(saved, dict) else None
    active = to_bcp47(previous or primary)
    if active not in allowed:
        active = to_bcp47(primary)
    return CallLanguageSession(
        tenant_id=config.company_id, call_session_id=str(call.id),
        primary_locale=primary, active_locale=active, allowed_locales=allowed,
    )


__all__ = [
    "VOICE_ACTION_TOOLS",
    "VOICE_NATIVE_TOOLS",
    "VOICE_TOOL_ALIASES",
    "VOICE_WRITE_TOOLS",
    "VoiceModuleAction",
    "action_for_tool",
    "actions_for_module",
    "catalog_modules",
    "is_voice_native_tool",
    "known_action",
    "tools_for_action",
    "tools_for_grants",
    "voice_agent_language",
]
