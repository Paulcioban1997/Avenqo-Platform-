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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolUnavailableError
from backend.app.models.commerce_connection import NormalizedCommerceRecord

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
    return {
        "product_name": _safe_str(data.get("product_name") or data.get("name")),
        "product_id": _safe_str(data.get("product_id") or data.get("id")),
        "sku": _safe_str(data.get("sku")),
        "unit_price": _safe_float(
            data.get("unit_price") or data.get("price") or data.get("regular_price")
        ),
        "inventory_level": _safe_float(
            data.get("inventory_level") or data.get("stock_quantity")
        ),
        "stock_quantity": _safe_float(
            data.get("stock_quantity") or data.get("inventory_level")
        ),
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


class GetProductDetailTool(AITool):
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

        base_query = (
            select(NormalizedCommerceRecord)
            .where(
                NormalizedCommerceRecord.company_id == company_id,
                NormalizedCommerceRecord.entity_type.in_(_PRODUCT_ENTITY_TYPES),
                NormalizedCommerceRecord.deleted.is_(False),
            )
            .order_by(NormalizedCommerceRecord.source_updated_at.desc())
        )

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

        products = [_product_to_dict(r) for r in records]
        source_refs = tuple({str(r.id) for r in records})

        logger.info(
            "commerce_product_lookup tenant_id=%s query=%r found=%d",
            company_id,
            search_label,
            len(products),
        )

        if len(products) == 1:
            return ToolResult(
                success=True,
                data={"found": True, "product": products[0]},
                source_refs=source_refs,
            )

        return ToolResult(
            success=True,
            data={"found": True, "matches": len(products), "products": products},
            source_refs=source_refs,
        )


# ---------------------------------------------------------------------------
# GetInventorySummaryTool — résumé stock tous produits (implémentation réelle)
# ---------------------------------------------------------------------------

class InventorySummaryArgs(ToolArguments):
    low_stock_threshold: int = 10


class GetInventorySummaryTool(AITool):
    name = "get_inventory_summary"
    description = (
        "Return a summary of the current inventory levels for all products in the "
        "tenant's connected commerce data (WooCommerce, Shopify, CSV). "
        "Shows total products, out-of-stock count, low-stock count, and lists "
        "products needing attention. Always reads live data — never invents values."
    )
    input_schema = InventorySummaryArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: InventorySummaryArgs) -> ToolResult:
        company_id = context.tenant.company_id

        try:
            records = list(
                self._session.scalars(
                    select(NormalizedCommerceRecord)
                    .where(
                        NormalizedCommerceRecord.company_id == company_id,
                        NormalizedCommerceRecord.entity_type.in_(_PRODUCT_ENTITY_TYPES),
                        NormalizedCommerceRecord.deleted.is_(False),
                    )
                    .order_by(NormalizedCommerceRecord.source_updated_at.desc())
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
            },
            source_refs=source_refs,
        )
