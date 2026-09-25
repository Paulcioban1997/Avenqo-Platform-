"""Façade HTTP orientée métier du module RetailSense."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.retail import get_retail_assistant
from backend.app.dependencies.tenant_business import (
    get_tenant_analytics_service,
    get_tenant_customers_service,
    get_tenant_products_service,
    get_tenant_sales_service,
)
from backend.app.ai.tools.business.analytics import compute_customer_portfolio
from backend.app.schemas.retail_assistant import RetailAssistantRequest, RetailAssistantResponse
from backend.app.schemas.retail_sources import (
    RetailSourceResponse,
    RetailSourceSelectionRequest,
    RetailSourceStateRequest,
)
from backend.app.services.retail_source_service import (
    RetailSourceNotFound,
    RetailSourceService,
)
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.tenant_customers_service import TenantCustomersService
from backend.app.services.tenant_products_service import TenantProductsService
from backend.app.services.tenant_sales_service import TenantSalesService
from modules.entitlements import ModuleAccessDenied
from modules.retailsense.assistant import RetailAssistantService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/retail", tags=["retail"])


@router.get("/sources", response_model=list[RetailSourceResponse])
def retail_sources(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[RetailSourceResponse]:
    return [
        RetailSourceResponse.model_validate(source, from_attributes=True)
        for source in RetailSourceService(db).list_sources(tenant)
    ]


@router.put("/sources/active", response_model=RetailSourceResponse)
def select_retail_source(
    request: RetailSourceSelectionRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> RetailSourceResponse:
    try:
        source = RetailSourceService(db).select_source(
            tenant,
            source_type=request.source_type,
            source_id=request.source_id,
        )
    except RetailSourceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retail source not found",
        ) from exc
    return RetailSourceResponse.model_validate(source, from_attributes=True)


@router.put("/sources/enabled", response_model=RetailSourceResponse)
def set_retail_source_enabled(
    request: RetailSourceStateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> RetailSourceResponse:
    try:
        source = RetailSourceService(db).set_source_enabled(
            tenant,
            source_type=request.source_type,
            source_id=request.source_id,
            enabled=request.enabled,
        )
    except RetailSourceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retail source not found",
        ) from exc
    return RetailSourceResponse.model_validate(source, from_attributes=True)


@router.post("/assistant", response_model=RetailAssistantResponse)
def ask_retail_assistant(
    request: RetailAssistantRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    assistant: RetailAssistantService = Depends(get_retail_assistant),
    db: Session = Depends(get_db),
) -> RetailAssistantResponse:
    active_source_name = None
    active_source_id_str = None
    if request.source_id and request.source_type:
        try:
            source = RetailSourceService(db).select_source(
                tenant, source_type=request.source_type, source_id=request.source_id
            )
            active_source_name = source.display_name
            active_source_id_str = str(source.id)
        except Exception:
            pass

    if not active_source_name:
        sources = RetailSourceService(db).list_sources(tenant)
        active_src = next((s for s in sources if s.active), None)
        if active_src:
            active_source_name = active_src.display_name
            active_source_id_str = str(active_src.id)

    try:
        reply = assistant.answer(tenant, request.question)
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RetailAssistantResponse(
        answer=reply.answer,
        suggested_actions=list(reply.suggested_actions),
        grounded_source=f"Analyse basée sur : [{active_source_name}]" if active_source_name else None,
        source_id=active_source_id_str,
    )


@router.get("/status")
def retail_status(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    analytics: TenantAnalyticsService = Depends(get_tenant_analytics_service),
):
    """Report only tenant sources enabled for shared Retail analytics."""
    from backend.app.services.tenant_products_service import TenantProductsService

    sources = [source for source in RetailSourceService(db).list_sources(tenant) if source.enabled]
    snapshot = analytics.load(tenant)
    product_source = snapshot.source_for(frozenset({"product_id"})) or snapshot.source_for(
        frozenset({"product_name"})
    )
    order_source = snapshot.source_for(frozenset({"order_id"}))
    customer_source = snapshot.source_for(frozenset({"customer_id"}))
    product_count = len(TenantProductsService.portfolio(product_source)) if product_source else 0
    order_count = (
        len({str(row.get("order_id")) for row in snapshot._canonical_rows(order_source)
             if row.get("order_id") is not None})
        if order_source else 0
    )
    customer_count = (
        len(compute_customer_portfolio(customer_source))
        if customer_source else 0
    )
    connection_sources = [source for source in sources if source.source_type == "connector"]
    connection = connection_sources[0] if len(connection_sources) == 1 else None

    return {
        "is_connected": bool(sources),
        "provider": connection.provider if connection else None,
        "store_url": connection.display_name if connection else None,
        "status": connection.status if connection else ("READY" if sources else "DISCONNECTED"),
        "last_synced_at": connection.last_synchronized_at.isoformat() if connection and connection.last_synchronized_at else None,
        "records_count": (product_count + order_count + customer_count),
        "product_count": product_count,
        "order_count": order_count,
        "customer_count": customer_count,
    }


def _extract_product_fields(d: dict) -> tuple[str, str, float, int]:
    name = str(d.get("product_name") or d.get("name") or d.get("title") or "Produit sans nom")
    variants = d.get("variants") or []
    v0 = variants[0] if isinstance(variants, list) and variants else {}

    sku = str(d.get("sku") or v0.get("sku") or d.get("id") or "—")

    price_val = d.get("unit_price") or d.get("price") or d.get("regular_price") or v0.get("unit_price") or 0.0
    try:
        price = float(price_val)
    except (ValueError, TypeError):
        price = 0.0

    stock_val = d.get("inventory_level") or d.get("stock_quantity")
    if stock_val is None and variants and isinstance(variants, list):
        stock_val = sum(int(v.get("inventory_level") or 0) for v in variants)
    try:
        stock = int(stock_val or 0)
    except (ValueError, TypeError):
        stock = 0

    return name, sku, price, stock


@router.get("/products")
def list_retail_products(
    tenant: TenantContext = Depends(get_tenant_context),
    service: TenantProductsService = Depends(get_tenant_products_service),
    limit: int = 100,
):
    """Retourne le portefeuille produit consolidé depuis les sources activées."""
    result = service.build(tenant, page=1, page_size=min(max(limit, 1), 500))
    products = []
    for item in result["items"]:
        stock = item.get("stock_level")
        products.append({
            "id": str(item["product_id"]),
            "source_record_id": str(item["product_id"]),
            "provider": "dataset",
            "product_name": item.get("name") or str(item["product_id"]),
            "sku": str(item.get("sku") or item["product_id"]),
            "product_category": item.get("category") or "Général",
            "unit_price": float(item.get("average_price") or 0),
            "stock_quantity": int(float(stock)) if stock is not None else 0,
            "stock_status": "instock" if stock is not None and float(stock) > 0 else "unknown",
            "store_url": None,
        })

    return {
        "products": products,
        "total": result["pagination"]["total"],
        "store_url": None,
        "provider": None,
    }


@router.get("/orders")
def list_retail_orders(
    tenant: TenantContext = Depends(get_tenant_context),
    analytics: TenantAnalyticsService = Depends(get_tenant_analytics_service),
    limit: int = 100,
):
    """Retourne des commandes agrégées depuis les lignes des datasets activés."""
    from backend.app.ai.tools.business.analytics import _reverse_mapping

    snapshot = analytics.load(tenant)
    source = snapshot.source_for(frozenset({"order_id"}))
    orders = []
    if source is not None:
        reverse = _reverse_mapping(source.canonical_columns)
        grouped: dict[str, dict[str, object]] = {}
        for row in source.rows:
            raw_order_id = row.get(reverse.get("order_id", ""))
            if raw_order_id is None or not str(raw_order_id).strip():
                continue
            order_id = str(raw_order_id).strip()
            order = grouped.setdefault(order_id, {
                "id": order_id,
                "source_record_id": order_id,
                "order_number": order_id,
                "customer_name": str(row.get(reverse.get("customer_name", "")) or row.get(reverse.get("customer_id", "")) or "—"),
                "total_amount": 0.0,
                "currency": snapshot.currency,
                "status": str(row.get(reverse.get("order_status", "")) or "completed"),
                "created_at": row.get(reverse.get("order_timestamp", "")),
            })
            try:
                order["total_amount"] = float(order["total_amount"]) + float(row.get(reverse.get("total_amount", "")) or 0)
            except (TypeError, ValueError):
                pass
        orders = list(grouped.values())
    orders.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {"orders": orders[:min(max(limit, 1), 500)], "total": len(orders)}


@router.get("/customers")
def list_retail_customers(
    tenant: TenantContext = Depends(get_tenant_context),
    service: TenantCustomersService = Depends(get_tenant_customers_service),
    limit: int = 100,
):
    """Retourne les clients consolidés depuis les datasets activés."""
    result = service.build(tenant, page=1, page_size=min(max(limit, 1), 500))
    customers = [
        {
            "id": str(item["customer_id"]),
            "source_record_id": str(item["customer_id"]),
            "name": str(item.get("name") or item["customer_id"]),
            "email": str(item.get("email") or "—"),
            "total_spent": float(item.get("total_value") or 0),
            "orders_count": int(item.get("orders") or 0),
        }
        for item in result["items"]
    ]

    return {"customers": customers, "total": result["pagination"]["total"]}


@router.get("/inventory")
def list_retail_inventory(
    tenant: TenantContext = Depends(get_tenant_context),
    products_service: TenantProductsService = Depends(get_tenant_products_service),
    limit: int = 100,
):
    """Retourne l'inventaire disponible sur les produits des sources activées."""
    product_result = products_service.build(
        tenant, page=1, page_size=min(max(limit, 1), 500)
    )

    items = []
    anomalies = []
    for product in product_result["items"]:
        stock_value = product.get("stock_level")
        name = str(product.get("name") or product["product_id"])
        sku = str(product.get("sku") or product["product_id"])
        price = float(product.get("unit_price") or 0)
        stock = int(float(stock_value)) if stock_value is not None else None
        product_id = str(product["product_id"])

        item = {
            "id": product_id,
            "product_name": name,
            "sku": sku,
            "stock_quantity": stock,
            "unit_price": price,
            "status": (
                "unknown" if stock is None
                else "critical" if stock <= 5
                else "warning" if stock <= 15
                else "normal"
            ),
        }
        items.append(item)

        if stock is not None and stock <= 5:
            anomalies.append({
                "id": f"crit-{product_id}",
                "product": name,
                "sku": sku,
                "currentStock": stock,
                "safetyThreshold": 15,
                "type": "stockout_risk",
                "severity": "critical",
                "message": f"Rupture imminente : seulement {stock} unités restantes en stock.",
            })
        elif stock is not None and stock > 200:
            anomalies.append({
                "id": f"over-{product_id}",
                "product": name,
                "sku": sku,
                "currentStock": stock,
                "safetyThreshold": 50,
                "type": "overstock",
                "severity": "medium",
                "message": f"Surstock détecté : {stock} unités disponibles. Risque d'immobilisation de trésorerie.",
            })

    return {
        "inventory": items,
        "total": len(items),
        "anomalies": anomalies,
    }