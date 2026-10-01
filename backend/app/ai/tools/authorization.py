"""Database-backed authorization for every AI tool invocation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.exceptions import ToolAuthorizationError
from backend.app.assistants.registry import AssistantRegistry
from backend.app.core.permissions import permissions_for
from backend.app.models import CompanyMembership, User
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.ai.tools.plans import plan_meets_minimum


class ToolAuthorizationPolicy:
    """Rechecks the live membership and entitlements at the execution boundary."""

    def __init__(self, db: Session, agents: AssistantRegistry) -> None:
        self._db = db
        self._agents = agents

    def authorize(self, tool: AITool, context: ToolExecutionContext) -> None:
        user = self._db.get(User, context.user_id)
        if (
            user is None
            or not user.is_active
            or user.company_id != context.tenant.company_id
        ):
            raise ToolAuthorizationError("The authenticated user cannot access this tenant.")

        membership = self._db.scalar(
            select(CompanyMembership).where(
                CompanyMembership.user_id == context.user_id,
                CompanyMembership.company_id == context.tenant.company_id,
                CompanyMembership.is_active.is_(True),
            )
        )
        if membership is None:
            raise ToolAuthorizationError("An active tenant membership is required.")

        permissions = frozenset(permissions_for(membership.role))
        if not set(tool.required_permissions).issubset(permissions):
            raise ToolAuthorizationError("The membership role cannot run this tool.")

        selected_agent_id = context.authorized_tool_agents.get(
            tool.name,
            context.selected_agent_id,
        )
        if not selected_agent_id:
            raise ToolAuthorizationError("A selected agent is required to run this tool.")
        agent = self._agents.get(selected_agent_id)
        if agent is None or not agent.status.is_executable:
            raise ToolAuthorizationError("The selected agent is not executable.")
        if tool.agent_ids and agent.agent_id not in tool.agent_ids:
            raise ToolAuthorizationError("The tool is not owned by the selected agent.")
        if tool.name not in agent.allowed_tool_names:
            raise ToolAuthorizationError("The selected agent is not allowed to run this tool.")
        if not set(agent.required_permissions).issubset(permissions):
            raise ToolAuthorizationError("The membership role cannot use this agent.")

        entitlements = ModuleEntitlementService(self._db)
        plan_code = entitlements.get_company_plan(context.tenant).code.value
        if not plan_meets_minimum(plan_code, agent.minimum_plan):
            raise ToolAuthorizationError("The current plan cannot use this agent.")
        if not plan_meets_minimum(plan_code, tool.minimum_plan):
            raise ToolAuthorizationError("The current plan cannot run this tool.")

        required_entitlements = set(agent.required_entitlements)
        if agent.module_code:
            required_entitlements.add(agent.module_code)
        required_entitlements.update(tool.required_entitlements)
        active_modules = set(entitlements.get_active_modules(context.tenant))
        if not required_entitlements.issubset(active_modules):
            raise ToolAuthorizationError("The required subscription module is not active.")

        required_capabilities = set(agent.required_capabilities)
        required_capabilities.update(tool.required_capabilities)
        if tool.requires_capability:
            required_capabilities.add(tool.requires_capability)
        if not required_capabilities.issubset(agent.capabilities):
            raise ToolAuthorizationError("The selected agent does not declare the tool capability.")
        if not required_capabilities.issubset(context.capabilities):
            raise ToolAuthorizationError("The tenant does not have the required capability.")

        if tool.mutates:
            if tool.read_only or not tool.mutation_capabilities:
                raise ToolAuthorizationError("The mutating tool has no valid mutation policy.")
            if tool.confirmation_policy != agent.confirmation_policy:
                raise ToolAuthorizationError("The tool confirmation policy does not match the selected agent.")
            if not tool.mutation_capabilities.issubset(agent.mutation_capabilities):
                raise ToolAuthorizationError("The selected agent cannot perform this mutation.")
            if not tool.mutation_capabilities.issubset(agent.supported_operations | agent.mutation_capabilities):
                raise ToolAuthorizationError("The selected agent does not support this mutation.")
        elif not tool.read_only:
            raise ToolAuthorizationError("A non-read-only tool must declare its mutation capability.")