from fastapi import Depends

from backend.app.ai.tools.registry import ToolRegistry
from backend.app.assistants.registry import AssistantRegistry, build_default_assistant_registry
from backend.app.dependencies.ai_tools import get_business_tool_registry


def get_assistant_registry(
    tools: ToolRegistry = Depends(get_business_tool_registry),
) -> AssistantRegistry:
    return build_default_assistant_registry(tools)
