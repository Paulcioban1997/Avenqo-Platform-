"""Construction du registre d'outils Avenqo et résolution des capacités tenant.

`resolve_tenant_capabilities` détermine quelles capacités optionnelles
(au-delà des données de vente de base) le tenant possède réellement, pour
que `ToolRegistry.available_for` ne propose jamais un outil inutilisable.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.ai.tools.business.customer_tools import GetCustomerSegmentsTool, GetCustomerSummaryTool
from backend.app.ai.tools.business.inventory_tools import GetInventorySummaryTool
from backend.app.ai.tools.business.sales_tools import (
    GetBusinessOverviewTool,
    GetSalesComparisonTool,
    GetSalesSummaryTool,
    GetSalesTrendTool,
    GetTopProductsTool,
)
from backend.app.ai.tools.registry import ToolRegistry
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.prediction_runtime import resolve_active_model_type
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService

RETAIL_MODULE_CODE = "retail"


def build_business_tool_registry(
    session: Session,
    ingestion: CompanyDatasetIngestionService,
    prediction_service: PredictionService,
) -> ToolRegistry:
    """Enregistre tous les outils métier Avenqo, y compris ceux non disponibles."""

    registry = ToolRegistry()
    registry.register(GetBusinessOverviewTool(session, ingestion))
    registry.register(GetSalesSummaryTool(session, ingestion))
    registry.register(GetSalesTrendTool(session, ingestion))
    registry.register(GetSalesComparisonTool(session, ingestion))
    registry.register(GetTopProductsTool(session, ingestion))
    registry.register(GetCustomerSummaryTool(session, ingestion))
    registry.register(GetCustomerSegmentsTool(session, prediction_service))
    registry.register(GetInventorySummaryTool())  # prepared, always unavailable today
    return registry


def resolve_tenant_capabilities(
    session: Session, tenant: TenantContext, prediction_service: PredictionService
) -> frozenset[str]:
    """Capacités optionnelles réellement disponibles pour ce tenant (pas d'inventaire)."""

    capabilities: set[str] = set()
    if resolve_active_model_type(session, tenant, RETAIL_MODULE_CODE, "segmentation") is not None:
        capabilities.add("segmentation")
    return frozenset(capabilities)
