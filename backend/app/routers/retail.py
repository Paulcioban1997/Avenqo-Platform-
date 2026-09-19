"""Façade HTTP orientée métier du module RetailSense."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.retail import get_retail_assistant
from backend.app.schemas.retail_assistant import RetailAssistantRequest, RetailAssistantResponse
from backend.app.schemas.retail_sources import (
    RetailSourceResponse,
    RetailSourceSelectionRequest,
)
from backend.app.services.retail_source_service import (
    RetailSourceNotFound,
    RetailSourceService,
)
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
):
    """Retourne le statut réel de connexion e-commerce du tenant pour le module Retail."""
    from backend.app.models.commerce_connection import CommerceConnection, CommerceConnectionStatus, NormalizedCommerceRecord
    from sqlalchemy import select, func

    connection = db.scalar(
        select(CommerceConnection)
        .where(
            CommerceConnection.company_id == tenant.company_id,
            CommerceConnection.status != CommerceConnectionStatus.DISCONNECTED.value,
        )
        .order_by(CommerceConnection.updated_at.desc())
    )

    product_count = db.scalar(
        select(func.count(NormalizedCommerceRecord.id))
        .where(
            NormalizedCommerceRecord.company_id == tenant.company_id,
            NormalizedCommerceRecord.entity_type.in_(["product", "products"]),
            NormalizedCommerceRecord.deleted.is_(False),
        )
    ) or 0

    order_count = db.scalar(
        select(func.count(NormalizedCommerceRecord.id))
        .where(
            NormalizedCommerceRecord.company_id == tenant.company_id,
            NormalizedCommerceRecord.entity_type.in_(["order", "orders"]),
            NormalizedCommerceRecord.deleted.is_(False),
        )
    ) or 0

    customer_count = db.scalar(
        select(func.count(NormalizedCommerceRecord.id))
        .where(
            NormalizedCommerceRecord.company_id == tenant.company_id,
            NormalizedCommerceRecord.entity_type.in_(["customer", "customers"]),
            NormalizedCommerceRecord.deleted.is_(False),
        )
    ) or 0

    return {
        "is_connected": connection is not None,
        "provider": connection.provider if connection else None,
        "store_url": connection.external_account_id if connection else None,
        "status": connection.status if connection else "DISCONNECTED",
        "last_synced_at": connection.last_successful_sync.isoformat() if connection and connection.last_successful_sync else None,
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
    db: Session = Depends(get_db),
    limit: int = 100,
):
    """Retourne la liste des produits normalisés synchronisés pour le tenant."""
    from backend.app.models.commerce_connection import CommerceConnection, CommerceConnectionStatus, NormalizedCommerceRecord
    from sqlalchemy import select

    connection = db.scalar(
        select(CommerceConnection)
        .where(
            CommerceConnection.company_id == tenant.company_id,
            CommerceConnection.status != CommerceConnectionStatus.DISCONNECTED.value,
        )
        .order_by(CommerceConnection.updated_at.desc())
    )
    store_url = connection.external_account_id if connection else None

    records = db.scalars(
        select(NormalizedCommerceRecord)
        .where(
            NormalizedCommerceRecord.company_id == tenant.company_id,
            NormalizedCommerceRecord.entity_type.in_(["product", "products"]),
            NormalizedCommerceRecord.deleted.is_(False),
        )
        .order_by(NormalizedCommerceRecord.updated_at.desc())
        .limit(limit)
    ).all()

    products = []
    for r in records:
        d = r.normalized_data or {}
        name, sku, price, stock = _extract_product_fields(d)
        category = str(d.get("product_category") or d.get("category") or "Général")
        stock_status = "instock" if stock > 0 else (d.get("stock_status") or "outofstock")

        products.append({
            "id": str(r.id),
            "source_record_id": r.source_record_id,
            "provider": r.provider,
            "product_name": name,
            "sku": sku,
            "product_category": category,
            "unit_price": price,
            "stock_quantity": stock,
            "stock_status": stock_status,
            "store_url": store_url,
        })

    return {
        "products": products,
        "total": len(products),
        "store_url": store_url,
        "provider": connection.provider if connection else None,
    }


@router.get("/orders")
def list_retail_orders(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    limit: int = 100,
):
    """Retourne la liste des commandes normalisées synchronisées pour le tenant."""
    from backend.app.models.commerce_connection import NormalizedCommerceRecord
    from sqlalchemy import select

    records = db.scalars(
        select(NormalizedCommerceRecord)
        .where(
            NormalizedCommerceRecord.company_id == tenant.company_id,
            NormalizedCommerceRecord.entity_type.in_(["order", "orders"]),
            NormalizedCommerceRecord.deleted.is_(False),
        )
        .order_by(NormalizedCommerceRecord.updated_at.desc())
        .limit(limit)
    ).all()

    orders = []
    for r in records:
        d = r.normalized_data or {}
        orders.append({
            "id": str(r.id),
            "source_record_id": r.source_record_id,
            "order_number": str(d.get("order_number") or d.get("number") or d.get("id") or r.source_record_id),
            "customer_name": str(d.get("customer_name") or (f"{d.get('billing', {}).get('first_name', '')} {d.get('billing', {}).get('last_name', '')}").strip() or "Client"),
            "total_amount": float(d.get("total_amount") or d.get("total") or 0.0),
            "currency": str(d.get("currency") or "CAD"),
            "status": str(d.get("status") or "completed"),
            "created_at": d.get("date_created") or d.get("created_at") or (r.created_at.isoformat() if r.created_at else None),
        })

    return {"orders": orders, "total": len(orders)}


@router.get("/customers")
def list_retail_customers(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    limit: int = 100,
):
    """Retourne la liste des clients normalisés synchronisés pour le tenant."""
    from backend.app.models.commerce_connection import NormalizedCommerceRecord
    from sqlalchemy import select

    records = db.scalars(
        select(NormalizedCommerceRecord)
        .where(
            NormalizedCommerceRecord.company_id == tenant.company_id,
            NormalizedCommerceRecord.entity_type.in_(["customer", "customers"]),
            NormalizedCommerceRecord.deleted.is_(False),
        )
        .order_by(NormalizedCommerceRecord.updated_at.desc())
        .limit(limit)
    ).all()

    customers = []
    for r in records:
        d = r.normalized_data or {}
        name = str(d.get("name") or f"{d.get('first_name', '')} {d.get('last_name', '')}".strip() or "Client")
        customers.append({
            "id": str(r.id),
            "source_record_id": r.source_record_id,
            "name": name,
            "email": str(d.get("email") or "—"),
            "total_spent": float(d.get("total_spent") or 0.0),
            "orders_count": int(d.get("orders_count") or 0),
        })

    return {"customers": customers, "total": len(customers)}


@router.get("/inventory")
def list_retail_inventory(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    limit: int = 100,
):
    """Retourne l'inventaire avec détection des ruptures et des surstocks."""
    from backend.app.models.commerce_connection import NormalizedCommerceRecord
    from sqlalchemy import select

    records = db.scalars(
        select(NormalizedCommerceRecord)
        .where(
            NormalizedCommerceRecord.company_id == tenant.company_id,
            NormalizedCommerceRecord.entity_type.in_(["product", "products"]),
            NormalizedCommerceRecord.deleted.is_(False),
        )
        .order_by(NormalizedCommerceRecord.updated_at.desc())
        .limit(limit)
    ).all()

    items = []
    anomalies = []
    for r in records:
        d = r.normalized_data or {}
        name, sku, price, stock = _extract_product_fields(d)

        item = {
            "id": str(r.id),
            "product_name": name,
            "sku": sku,
            "stock_quantity": stock,
            "unit_price": price,
            "status": "critical" if stock <= 5 else ("warning" if stock <= 15 else "normal"),
        }
        items.append(item)

        if stock <= 5:
            anomalies.append({
                "id": f"crit-{r.id}",
                "product": name,
                "sku": sku,
                "currentStock": stock,
                "safetyThreshold": 15,
                "type": "stockout_risk",
                "severity": "critical",
                "message": f"Rupture imminente : seulement {stock} unités restantes en stock.",
            })
        elif stock > 200:
            anomalies.append({
                "id": f"over-{r.id}",
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