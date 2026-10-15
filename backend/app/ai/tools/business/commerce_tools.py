"""Outils métier Avenqo : données commerce normalisées (WooCommerce/Shopify/CSV).

Ces outils lisent directement `normalized_commerce_records` — la même table
utilisée par Retail Intelligence et les KPI Engine — garantissant une source
unique de vérité entre tous les composants Avenqo.

Isolation multi-tenant : toutes les requêtes filtrent `company_id = tenant.company_id`.
Fraîcheur : aucun cache applicatif — chaque appel outil lit la valeur la plus
récente en base (reflétant la dernière synchronisation WooCommerce/Shopify).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.base import RetailAITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolUnavailableError
from backend.app.models.commerce_connection import NormalizedCommerceRecord
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.data_freshness_service import DataFreshnessService
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.tenant_products_service import TenantProductsService

logger = logging.getLogger("avenqo.ai.commerce_tools")

_PRODUCT_ENTITY_TYPES = ("product", "products")
_INVENTORY_ENTITY_TYPES = ("inventory", "inventories")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _normalize_query(q: str) -> str:
    return q.lower().strip()


def _product_to_dict(record: NormalizedCommerceRecord) -> dict[str, object]:
    """Extrait les champs canoniques depuis le JSON normalisé d'un produit."""
    data: dict[str, Any] = record.normalized_data or {}
    price_val = data.get("unit_price")
    if price_val is None:
        price_val = data.get("price") if data.get("price") is not None else data.get("regular_price")

    inv_val = data.get("inventory_level")
    if inv_val is None:
        inv_val = data.get("stock_quantity")

    return {
        "product_name": _safe_str(data.get("product_name") or data.get("name")),
        "product_id": _safe_str(data.get("product_id") or data.get("id")),
        "sku": _safe_str(data.get("sku")),
        "unit_price": _safe_float(price_val),
        "inventory_level": _safe_float(inv_val),
        "stock_quantity": _safe_float(inv_val),
        "product_category": _safe_str(data.get("product_category") or data.get("category")),
        "in_stock": data.get("in_stock"),
        "stock_status": _safe_str(data.get("stock_status")),
        "source_updated_at": (
            record.source_updated_at.isoformat() if record.source_updated_at else None
        ),
        "connection_id": str(record.connection_id),
        "provider": record.provider,
    }


def _python_product_search(
    records: list[NormalizedCommerceRecord],
    *,
    product_name: str | None,
    product_id: str | None,
    sku: str | None,
) -> list[NormalizedCommerceRecord]:
    """Filtre Python pour SQLite et bases sans support JSON avancé."""
    result = []
    for r in records:
        data = r.normalized_data or {}
        if product_id is not None:
            if str(data.get("product_id") or data.get("id") or "") == str(product_id).strip():
                result.append(r)
            continue
        if sku is not None:
            if str(data.get("sku") or "").lower() == sku.lower().strip():
                result.append(r)
            continue
        if product_name is not None:
            name = str(data.get("product_name") or data.get("name") or "").lower()
            if _normalize_query(product_name) in name:
                result.append(r)
    return result


# ---------------------------------------------------------------------------
# GetProductDetailTool
# ---------------------------------------------------------------------------

class ProductDetailArgs(ToolArguments):
    product_name: str | None = None
    product_id: str | None = None
    sku: str | None = None
    source_scope: list[str] | str | None = None


class GetProductDetailTool(RetailAITool):
    name = "get_product_detail"
    description = (
        "Return the current stock level (inventory_level), price (unit_price), SKU, "
        "and category for a specific product. Use when the user asks about a specific "
        "product's stock, price, or availability. Provide product_name, product_id "
        "or sku to look it up. Searches the tenant's connected commerce data "
        "(WooCommerce, Shopify, CSV) in real time — never returns cached or invented values."
    )
    input_schema = ProductDetailArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: ProductDetailArgs) -> ToolResult:
        company_id = context.tenant.company_id

        if not arguments.product_name and not arguments.product_id and not arguments.sku:
            return ToolResult(
                success=False,
                error="Please provide a product name, product ID, or SKU to look up.",
            )

        from backend.app.services.retail_source_service import RetailSourceService

        active_source = RetailSourceService(self._session).active_selection(context.tenant)
        if active_source is not None and active_source.source_type == "dataset":
            return ToolResult(
                success=True,
                data={
                    "found": False,
                    "query": arguments.product_name or arguments.product_id or arguments.sku,
                    "message": "La source active est un dataset importé. Consultez la vue Ventes pour ces données.",
                },
            )

        scope_conn_ids: list[UUID] | None = None
        if arguments.source_scope is not None:
            raw_scopes = [arguments.source_scope] if isinstance(arguments.source_scope, str) else list(arguments.source_scope)
            if "all" not in [s.lower() for s in raw_scopes]:
                parsed = []
                for s in raw_scopes:
                    try:
                        parsed.append(UUID(s))
                    except (ValueError, TypeError):
                        pass
                scope_conn_ids = parsed
        elif active_source is not None:
            if getattr(active_source, "source_type", None) in ("single", "connector") and getattr(active_source, "connection_id", None) is not None:
                scope_conn_ids = [active_source.connection_id]
            elif getattr(active_source, "source_type", None) == "custom_set":
                scope_conn_ids = list(getattr(active_source, "connection_ids", []) or [])

        base_query = (
            select(NormalizedCommerceRecord)
            .where(
                NormalizedCommerceRecord.company_id == company_id,
                NormalizedCommerceRecord.entity_type.in_(_PRODUCT_ENTITY_TYPES),
                NormalizedCommerceRecord.deleted.is_(False),
            )
        )
        if scope_conn_ids is not None:
            base_query = base_query.where(
                NormalizedCommerceRecord.connection_id.in_(scope_conn_ids)
            )
        base_query = base_query.order_by(NormalizedCommerceRecord.source_updated_at.desc())

        records: list[NormalizedCommerceRecord] = []

        # 1. Try PostgreSQL JSON operators (fast path)
        try:
            if arguments.product_id:
                pid = str(arguments.product_id).strip()
                rows = list(
                    self._session.scalars(
                        base_query.where(
                            NormalizedCommerceRecord.normalized_data["product_id"].astext == pid
                        ).limit(5)
                    ).all()
                )
            elif arguments.sku:
                sku = str(arguments.sku).strip().lower()
                rows = list(
                    self._session.scalars(
                        base_query.where(
                            func.lower(
                                NormalizedCommerceRecord.normalized_data["sku"].astext
                            ) == sku
                        ).limit(5)
                    ).all()
                )
            else:
                query_term = _normalize_query(arguments.product_name or "")
                rows = list(
                    self._session.scalars(
                        base_query.where(
                            func.lower(
                                NormalizedCommerceRecord.normalized_data["product_name"].astext
                            ).contains(query_term)
                        ).limit(10)
                    ).all()
                )
            records = rows
        except Exception:
            # 2. Python fallback (SQLite / older PG)
            all_rows = list(
                self._session.scalars(base_query.limit(500)).all()
            )
            records = _python_product_search(
                all_rows,
                product_name=arguments.product_name,
                product_id=arguments.product_id,
                sku=arguments.sku,
            )

        search_label = arguments.product_name or arguments.product_id or arguments.sku

        if not records:
            logger.info(
                "commerce_product_lookup tenant_id=%s query=%r found=0",
                company_id,
                search_label,
            )
            return ToolResult(
                success=True,
                data={
                    "found": False,
                    "query": search_label,
                    "message": (
                        f"No product matching '{search_label}' was found in your "
                        "connected commerce data."
                    ),
                },
            )

        from backend.app.models.commerce_connection import CommerceConnection
        conn_map: dict[UUID, str] = {}
        if records:
            conn_ids = {r.connection_id for r in records if r.connection_id}
            conns = self._session.scalars(
                select(CommerceConnection).where(CommerceConnection.id.in_(conn_ids))
            ).all()
            conn_map = {c.id: (c.display_name or c.provider) for c in conns}

        products = []
        for r in records:
            p = _product_to_dict(r)
            cid = r.connection_id
            p["store_name"] = conn_map.get(cid, str(p.get("provider") or "Commerce Store"))
            products.append(p)

        source_refs = tuple({str(r.id) for r in records})
        store_names = sorted(set(conn_map.values())) if conn_map else ["Catalogue connecté"]
        provenance = f"Données issues de : {', '.join(store_names)}"

        breakdown_by_source = {}
        for p in products:
            s_name = p.get("store_name") or "Autre"
            breakdown_by_source.setdefault(s_name, []).append({
                "product_name": p.get("product_name"),
                "sku": p.get("sku"),
                "inventory_level": p.get("inventory_level"),
                "unit_price": p.get("unit_price"),
            })

        logger.info(
            "commerce_product_lookup tenant_id=%s query=%r found=%d",
            company_id,
            search_label,
            len(products),
        )

        if len(products) == 1:
            return ToolResult(
                success=True,
                data={
                    "found": True,
                    "product": products[0],
                    "provenance": provenance,
                    "breakdown_by_source": breakdown_by_source,
                },
                source_refs=source_refs,
            )

        return ToolResult(
            success=True,
            data={
                "found": True,
                "matches": len(products),
                "products": products,
                "provenance": provenance,
                "breakdown_by_source": breakdown_by_source,
            },
            source_refs=source_refs,
        )


# ---------------------------------------------------------------------------
# GetInventorySummaryTool — résumé stock tous produits (implémentation réelle)
# ---------------------------------------------------------------------------

class InventorySummaryArgs(ToolArguments):
    low_stock_threshold: int = 10
    source_scope: list[str] | str | None = None


class GetInventorySummaryTool(RetailAITool):
    name = "get_inventory_summary"
    description = (
        "Return a summary of the current inventory levels for all products in the "
        "tenant's currently selected business data (WooCommerce, Shopify or CSV snapshot). "
        "Shows total products, out-of-stock count, low-stock count, and lists "
        "products needing attention. Reports the actual source freshness and never labels a sync snapshot as live."
    )
    input_schema = InventorySummaryArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService | None = None) -> None:
        self._session = session
        self._ingestion = ingestion

    async def run(self, context: ToolExecutionContext, arguments: InventorySummaryArgs) -> ToolResult:
        company_id = context.tenant.company_id
        if self._ingestion is not None:
            snapshot = TenantAnalyticsService(self._session, self._ingestion).load(context.tenant)
            source = snapshot.source_for(frozenset({"product_id"})) or snapshot.source_for(frozenset({"product_name"}))
            freshness = DataFreshnessService().for_snapshot(snapshot)
            if source is None:
                return ToolResult(success=False, data={
                    "inventory_state": "UNAVAILABLE",
                    "error": "No inventory-capable selected source is available.",
                    "data_freshness": freshness.as_dict(),
                })
            products = TenantProductsService.portfolio(source)
            threshold = max(0, arguments.low_stock_threshold)
            out_of_stock, low_stock, healthy, unknown = [], [], [], []
            for product in products:
                stock = product.get("stock_level")
                item = {
                    "product_id": str(product["product_id"]),
                    "name": product.get("name") or str(product["product_id"]),
                    "inventory_level": stock,
                }
                if stock is None:
                    unknown.append(item)
                elif float(stock) <= 0:
                    out_of_stock.append(item)
                elif float(stock) <= threshold:
                    low_stock.append(item)
                else:
                    healthy.append(item)
            return ToolResult(
                success=True,
                data={
                    "inventory_state": "READY" if not unknown else "PARTIAL",
                    "total_products": len(products),
                    "out_of_stock_count": len(out_of_stock),
                    "low_stock_count": len(low_stock),
                    "healthy_stock_count": len(healthy),
                    "unknown_stock_count": len(unknown),
                    "low_stock_threshold": threshold,
                    "out_of_stock": out_of_stock[:20],
                    "low_stock": low_stock[:20],
                    "unknown_stock": unknown[:20],
                    "source_ids": [str(source.dataset_id)],
                    "source_type": snapshot.active_source_provider or snapshot.active_source_type or "dataset",
                    "data_freshness": freshness.as_dict(),
                },
                source_refs=(str(source.dataset_id),),
            )
        from backend.app.services.retail_source_service import RetailSourceService

        active_source = RetailSourceService(self._session).active_selection(context.tenant)
        if active_source is not None and active_source.source_type == "dataset":
            return ToolResult(
                success=True,
                data={
                    "total_products": 0,
                    "message": (
                        "La source sélectionnée est un fichier importé. L'inventaire en direct nécessite une boutique connectée (WooCommerce ou Shopify)."
                    ),
                },
            )

        scope_conn_ids: list[UUID] | None = None
        if arguments.source_scope is not None:
            raw_scopes = [arguments.source_scope] if isinstance(arguments.source_scope, str) else list(arguments.source_scope)
            if "all" not in [s.lower() for s in raw_scopes]:
                parsed = []
                for s in raw_scopes:
                    try:
                        parsed.append(UUID(s))
                    except (ValueError, TypeError):
                        pass
                scope_conn_ids = parsed
        elif active_source is not None:
            if getattr(active_source, "source_type", None) in ("single", "connector") and getattr(active_source, "connection_id", None) is not None:
                scope_conn_ids = [active_source.connection_id]
            elif getattr(active_source, "source_type", None) == "custom_set":
                scope_conn_ids = list(getattr(active_source, "connection_ids", []) or [])

        try:
            inv_query = (
                select(NormalizedCommerceRecord)
                .where(
                    NormalizedCommerceRecord.company_id == company_id,
                    NormalizedCommerceRecord.entity_type.in_(_PRODUCT_ENTITY_TYPES),
                    NormalizedCommerceRecord.deleted.is_(False),
                )
            )
            if scope_conn_ids is not None:
                inv_query = inv_query.where(
                    NormalizedCommerceRecord.connection_id.in_(scope_conn_ids)
                )
            records = list(
                self._session.scalars(
                    inv_query.order_by(NormalizedCommerceRecord.source_updated_at.desc())
                ).all()
            )
        except Exception as exc:
            logger.exception(
                "commerce_inventory_summary_error tenant_id=%s", company_id
            )
            raise ToolUnavailableError(
                "Unable to read inventory data from the database."
            ) from exc

        if not records:
            return ToolResult(
                success=True,
                data={
                    "total_products": 0,
                    "message": (
                        "No product data is available in your connected commerce sources. "
                        "Connect a WooCommerce or Shopify store, or upload a product CSV."
                    ),
                },
            )

        threshold = max(0, arguments.low_stock_threshold)
        out_of_stock: list[dict[str, object]] = []
        low_stock: list[dict[str, object]] = []
        healthy: list[dict[str, object]] = []

        for r in records:
            p = _product_to_dict(r)
            level = p.get("inventory_level")
            name = p.get("product_name") or p.get("product_id") or "?"
            if level is None:
                continue
            item = {"name": name, "inventory_level": level}
            if float(level) <= 0:
                out_of_stock.append(item)
            elif float(level) <= threshold:
                low_stock.append(item)
            else:
                healthy.append(item)

        from backend.app.models.commerce_connection import CommerceConnection
        conn_map: dict[UUID, str] = {}
        if records:
            conn_ids = {r.connection_id for r in records if r.connection_id}
            conns = self._session.scalars(
                select(CommerceConnection).where(CommerceConnection.id.in_(conn_ids))
            ).all()
            conn_map = {c.id: (c.display_name or c.provider) for c in conns}

        breakdown_by_source: dict[str, dict[str, int]] = {}
        for r in records:
            s_name = conn_map.get(r.connection_id, r.provider or "Commerce Store")
            entry = breakdown_by_source.setdefault(s_name, {"total": 0, "out_of_stock": 0, "low_stock": 0})
            entry["total"] += 1
            p = _product_to_dict(r)
            lvl = p.get("inventory_level")
            if lvl is not None:
                if float(lvl) <= 0:
                    entry["out_of_stock"] += 1
                elif float(lvl) <= threshold:
                    entry["low_stock"] += 1

        store_names = sorted(set(conn_map.values())) if conn_map else ["Boutiques connectées"]
        provenance = f"Données issues de : {', '.join(store_names)}"

        source_refs = tuple({str(r.id) for r in records})

        logger.info(
            "commerce_inventory_summary tenant_id=%s total=%d out_of_stock=%d low_stock=%d",
            company_id,
            len(records),
            len(out_of_stock),
            len(low_stock),
        )

        return ToolResult(
            success=True,
            data={
                "total_products": len(records),
                "out_of_stock_count": len(out_of_stock),
                "low_stock_count": len(low_stock),
                "healthy_stock_count": len(healthy),
                "low_stock_threshold": threshold,
                "out_of_stock": out_of_stock[:20],
                "low_stock": low_stock[:20],
                "provenance": provenance,
                "breakdown_by_source": breakdown_by_source,
            },
            source_refs=source_refs,
        )
