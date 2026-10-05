from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from payments.plans import PUBLIC_PLANS


class GetSubscriptionOptionsTool(AITool):
    name = "get_subscription_options"
    description = (
        "Read the tenant's real subscription, enabled modules and canonical plan options. "
        "Explain missing modules, module limits and upgrades in the conversation language. "
        "Never activate a module, modify a subscription or charge money. "
        "Paid changes require the existing Billing workflow and explicit confirmation."
    )
    input_schema = ToolArguments
    agent_ids = frozenset({"tenant_capabilities", "voice"})
    read_only = True
    mutates = False

    def __init__(self, session: Session) -> None:
        self._entitlements = ModuleEntitlementService(session)

    async def run(self, context: ToolExecutionContext, arguments: ToolArguments) -> ToolResult:
        summary = self._entitlements.summary(context.tenant)
        return ToolResult(success=True, data={
            "subscription_plan": summary.plan_code,
            "subscription_status": summary.subscription_status,
            "enabled_modules": list(summary.active_modules),
            "module_limit": summary.module_limit,
            "remaining_module_slots": summary.remaining_module_slots,
            "modules": [{"key": item.key, "state": item.state.value, "active": item.active} for item in summary.modules],
            "plans": [{
                "code": plan.code.value,
                "name": plan.name,
                "selectable_modules": sorted(plan.selectable_modules),
                "module_limit": plan.max_selectable_modules,
                "requires_sales_contact": plan.requires_sales_contact,
                "monthly_price_usd": plan.monthly_price_usd,
            } for plan in PUBLIC_PLANS],
            "upgrade_route": "/billing",
            "paid_changes_require_confirmation": True,
            "subscription_changed": False,
        }, source_refs=("billing_accounts", "company_modules", "canonical_plan_catalog"))