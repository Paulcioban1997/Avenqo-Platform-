"""Voice caller scope: what an unauthenticated phone caller may do.

Security model (fail-closed):
- An unauthenticated caller is marked with ``PUBLIC_VOICE_CALLER_PERMISSION``.
- Such a caller may only use ``PUBLIC_VOICE_TOOLS`` (public booking flow).
- This is enforced twice: when tools are exposed to the LLM
  (``CentralAIService._tool_scope_for_request``) and again at the execution
  boundary (``ToolAuthorizationPolicy.authorize``), so a tool call the LLM
  produces on its own is still refused.
"""

from __future__ import annotations

PUBLIC_VOICE_CALLER_PERMISSION = "voice:public_caller"

# Public booking only. Reading or changing an existing appointment requires a
# verified customer identity and is deliberately excluded.
PUBLIC_VOICE_TOOLS: frozenset[str] = frozenset({
    "check_availability",
    "list_available_slots",
    "create_appointment",
})

# Permissions granted to an unauthenticated caller. The public marker is what
# restricts the tool scope; the CRM permissions only allow the public booking.
PUBLIC_VOICE_CALLER_PERMISSIONS: frozenset[str] = frozenset({
    "ai:use",
    "crm:appointments:read",
    "crm:appointments:write",
    PUBLIC_VOICE_CALLER_PERMISSION,
})


def is_public_voice_caller(permissions: frozenset[str] | set[str] | tuple[str, ...]) -> bool:
    return PUBLIC_VOICE_CALLER_PERMISSION in permissions


def public_voice_tool_allowed(tool_name: str) -> bool:
    return tool_name in PUBLIC_VOICE_TOOLS
