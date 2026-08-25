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
from backend.app.assistants.registry import RETAIL_TOOL_NAMES, build_default_assistant_registry
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


def test_future_assistants_resolve_as_coming_soon_and_cannot_execute() -> None:
    registry = build_default_assistant_registry()

    for slug in ("crm", "accounting", "legal", "marketing"):
        definition = registry.get(slug)
        assert definition is not None
        assert definition.status is AssistantStatus.COMING_SOON
        assert definition.status.is_executable is False
        assert definition.allowed_tool_names == frozenset()


def test_unknown_assistant_slug_resolves_to_none() -> None:
    registry = build_default_assistant_registry()

    assert registry.get("does-not-exist") is None


def test_list_available_contains_only_retail() -> None:
    registry = build_default_assistant_registry()

    available_slugs = {item.slug for item in registry.list_available()}

    assert available_slugs == {"retail"}


def test_retail_allowed_tool_names_matches_actual_business_tool_registry(db_session) -> None:
    """The declared allow-list must never drift from the real registry:
    no assistant should silently gain access to a tool it wasn't granted."""

    class _FakeIngestion:
        pass

    class _FakePredictionService:
        pass

    business_registry = build_business_tool_registry(db_session, _FakeIngestion(), _FakePredictionService())
    actual_tool_names = {tool.name for tool in business_registry.list_tools()}

    assert actual_tool_names == RETAIL_TOOL_NAMES
