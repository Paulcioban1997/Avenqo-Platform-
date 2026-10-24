"""Voice caller scope: what an unauthenticated phone caller may do.

Security model (fail-closed):
- An unauthenticated caller is marked with ``PUBLIC_VOICE_CALLER_PERMISSION``.
- Such a caller may ONLY use public tools (store info,
  and public booking ONLY IF the business actually configures bookable services).
- Under NO circumstance may a public caller access confidential sales numbers,
  orders, revenue, customer analytics, or internal stock valuations.
- This is enforced twice: when tools are exposed to the LLM
  (``CentralAIService._tool_scope_for_request``) and again at the execution
  boundary (``ToolAuthorizationPolicy.authorize``), so a tool call the LLM
  produces on its own is still refused.
"""

from __future__ import annotations

PUBLIC_VOICE_CALLER_PERMISSION = "voice:public_caller"

# Public business information; internal product records require personal auth.
PUBLIC_VOICE_BASE_TOOLS: frozenset[str] = frozenset({
    "get_business_info",
})

# Public booking tools - only permitted when tenant has CRM booking configured
PUBLIC_VOICE_CRM_TOOLS: frozenset[str] = frozenset({
    "check_availability",
    "list_available_slots",
    "create_appointment",
})

# Public retail catalog inquiry tools (products, prices, public inventory availability)
PUBLIC_VOICE_RETAIL_TOOLS: frozenset[str] = frozenset({
    "get_top_products",
    "get_product_detail",
    "get_inventory_summary",
})

# Union of all possible public tools for backward compatibility
PUBLIC_VOICE_TOOLS: frozenset[str] = (
    PUBLIC_VOICE_BASE_TOOLS | PUBLIC_VOICE_CRM_TOOLS | PUBLIC_VOICE_RETAIL_TOOLS
)

# Permissions granted to an unauthenticated caller. The public marker is what
# restricts the tool scope; the CRM permissions only allow the public booking,
# and data:read allows reading public retail product catalog and pricing.
PUBLIC_VOICE_CALLER_PERMISSIONS: frozenset[str] = frozenset({
    "ai:use",
    "data:read",
    "crm:appointments:read",
    "crm:appointments:write",
    PUBLIC_VOICE_CALLER_PERMISSION,
})


def is_public_voice_caller(permissions: frozenset[str] | set[str] | tuple[str, ...]) -> bool:
    return PUBLIC_VOICE_CALLER_PERMISSION in permissions


def public_voice_tool_allowed(
    tool_name: str,
    *,
    has_crm_booking: bool = True,
    has_retail: bool = True,
) -> bool:
    if tool_name in PUBLIC_VOICE_BASE_TOOLS:
        return True
    if tool_name in PUBLIC_VOICE_CRM_TOOLS:
        return has_crm_booking
    if tool_name in PUBLIC_VOICE_RETAIL_TOOLS:
        return has_retail
    return False


__all__ = [
    "PUBLIC_VOICE_BASE_TOOLS",
    "PUBLIC_VOICE_CALLER_PERMISSION",
    "PUBLIC_VOICE_CALLER_PERMISSIONS",
    "PUBLIC_VOICE_CRM_TOOLS",
    "PUBLIC_VOICE_RETAIL_TOOLS",
    "PUBLIC_VOICE_TOOLS",
    "is_public_voice_caller",
    "public_voice_tool_allowed",
]
