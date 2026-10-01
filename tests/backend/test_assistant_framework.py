"""AVENQO — Assistant Framework foundation tests.

Covers the minimal `AssistantDefinition`/`AssistantRegistry` abstraction:
Retail resolves AVAILABLE, future assistants resolve COMING_SOON and can
never execute, and Retail's declared tool allow-list matches exactly the
tools actually registered in the existing (unduplicated) business Tool
Registry factory.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.assistants.contracts import AssistantStatus
from backend.app.assistants.registry import build_default_assistant_registry
from backend.app.ai.tools.business.registry_factory import build_business_tool_registry
from backend.app.models import Base


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'assistant_framework.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def test_retail_assistant_resolves_as_available() -> None:
    registry = build_default_assistant_registry()

    retail = registry.get("retail")

    assert retail is not None
    assert retail.status is AssistantStatus.AVAILABLE
    assert retail.status.is_executable is True
    assert retail.module_code == "retail"


def test_registry_contains_only_implemented_agents_and_future_placeholders() -> None:
    registry = build_default_assistant_registry()

    for agent_id in ("retail", "crm", "accounting", "cross_agent"):
        definition = registry.get(agent_id)
        assert definition is not None
        assert definition.status is AssistantStatus.AVAILABLE
        assert definition.status.is_executable is True
    assert registry.get("marketing") is None
    assert registry.get("appointments") is None
    assert registry.get("workflow") is None
    assert registry.get("crm").allowed_tool_names == frozenset()
    assert registry.get("accounting").allowed_tool_names == frozenset()


def test_unavailable_assistant_cannot_execute() -> None:
    registry = build_default_assistant_registry()

    for slug in ("marketing", "ocr", "voice", "media", "legal", "workflow", "ai_agents"):
        assert registry.get(slug) is None


def test_unknown_assistant_slug_resolves_to_none() -> None:
    registry = build_default_assistant_registry()

    assert registry.get("does-not-exist") is None


def test_list_available_contains_only_implemented_agents() -> None:
    registry = build_default_assistant_registry()

    available_slugs = {item.slug for item in registry.list_available()}

    expected = {"retail", "crm", "accounting", "cross_agent", "platform_support"}
    assert available_slugs == expected


def test_retail_allowed_tool_names_matches_actual_business_tool_registry(db_session) -> None:
    """The declared allow-list must never drift from the real registry:
    no assistant should silently gain access to a tool it wasn't granted."""

    class _FakeIngestion:
        pass

    class _FakePredictionService:
        pass

    business_registry = build_business_tool_registry(db_session, _FakeIngestion(), _FakePredictionService())
    actual_tool_names = {tool.name for tool in business_registry.list_tools()}
    assistants = build_default_assistant_registry(business_registry)

    assert assistants.get("retail").allowed_tool_names == frozenset(
        tool.name for tool in business_registry.list_tools() if "retail" in tool.agent_ids
    )
    assert assistants.get("crm").allowed_tool_names == frozenset(
        tool.name for tool in business_registry.list_tools() if "crm" in tool.agent_ids
    )
    assert assistants.get("accounting").allowed_tool_names == frozenset(
        tool.name for tool in business_registry.list_tools() if "accounting" in tool.agent_ids
    )
    assert all(tool.agent_ids for tool in business_registry.list_tools())
    assert actual_tool_names == {tool.name for tool in business_registry.list_tools()}


def test_cross_agent_definition_is_not_a_union_of_domain_tool_allowlists() -> None:
    class _Tool:
        name = "get_cross_agent_business_health"
        agent_ids = frozenset({"cross_agent"})
        required_capabilities = frozenset()
        requires_capability = None

    class _ToolRegistry:
        def list_tools(self):
            return (_Tool(),)

    cross_agent = build_default_assistant_registry(_ToolRegistry()).get("cross_agent")

    assert cross_agent is not None
    assert cross_agent.allowed_tool_names == frozenset({"get_cross_agent_business_health"})
    assert cross_agent.required_entitlements == frozenset({"retail", "crm", "accounting"})
