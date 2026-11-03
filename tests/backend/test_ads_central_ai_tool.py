"""Tests for Ads tools in Central AI orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.business.marketing_tools import GetAdsPerformanceArgs, GetAdsPerformanceTool
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.models.base import Base
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ads_tool.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.mark.asyncio
async def test_get_ads_performance_tool_requires_marketing_entitlement(db_session):
    tool = GetAdsPerformanceTool(db_session)
    company_id = uuid4()
    user_id = uuid4()
    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company_id, user_id=user_id),
        user_id=user_id,
        permissions=frozenset(["ai:use", "data:read"]),
        request_id="req-123",
    )

    with patch.object(ModuleEntitlementService, "can_use_module", return_value=False):
        result = await tool.run(context, GetAdsPerformanceArgs(period="30d"))
        assert result.success is False
        assert result.data["code"] == "MODULE_NOT_ENTITLED"


@pytest.mark.asyncio
async def test_get_ads_performance_tool_returns_safe_metrics_when_entitled(db_session):
    tool = GetAdsPerformanceTool(db_session)
    company_id = uuid4()
    user_id = uuid4()
    context = ToolExecutionContext(
        tenant=TenantContext(company_id=company_id, user_id=user_id),
        user_id=user_id,
        permissions=frozenset(["ai:use", "data:read"]),
        request_id="req-123",
    )

    fake_summary = {
        "period": "last_30d",
        "currency": "CAD",
        "total_spend_cad": 450.75,
        "total_impressions": 12500,
        "total_clicks": 620,
        "total_conversions": 34,
        "average_ctr": 4.96,
        "average_cpc_cad": 0.73,
        "campaigns_count": 3,
        "active_campaigns_count": 2,
        "providers_connected": ["google_ads", "meta_ads"],
        "campaigns": [],
    }

    with patch.object(ModuleEntitlementService, "can_use_module", return_value=True), \
         patch("backend.app.services.ads_service.AdsService.get_combined_performance", AsyncMock(return_value=fake_summary)):
        result = await tool.run(context, GetAdsPerformanceArgs(period="last_30d"))

    assert result.success is True
    assert result.data["total_spend_cad"] == 450.75
    assert result.data["total_conversions"] == 34
    assert result.data["currency"] == "CAD"
    assert "ads_reporting" in result.source_refs
