"""Service transactionnel multi-tenant de réservation et mise de côté de produits en boutique.

Garantit:
1. Persistance intégrale en base de données de chaque réservation.
2. Déduction de stock concurrentiel pour empêcher les doubles réservations.
3. Vérification de la fraîcheur de la source (connecteur LIVE vs import HISTORICAL_IMPORT).
4. Statuts de cycle de vie : PENDING, CONFIRMED, COLLECTED, CANCELLED, EXPIRED.
5. Visibilité pour l'équipe du magasin via l'interface et journal d'audit.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import hashlib
import logging
import time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.commerce_connection import CommerceConnection, NormalizedCommerceRecord
from backend.app.models.product_reservation import ProductReservation, ReservationStatus

logger = logging.getLogger("avenqo.retail.reservations")

_PRODUCT_ENTITY_TYPES = ("product", "products")


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
    data: dict[str, Any] = record.normalized_data or {}
    variants = data.get("variants") or []

    price_val = data.get("unit_price")
    if price_val is None:
        price_val = data.get("price") if data.get("price") is not None else data.get("regular_price")
    if price_val is None and isinstance(variants, list) and variants:
        price_val = variants[0].get("unit_price") or variants[0].get("price")

    inv_val = data.get("inventory_level")
    if inv_val is None:
        inv_val = data.get("stock_quantity")
    if inv_val is None and isinstance(variants, list) and variants:
        inv_val = sum(v.get("inventory_level", 0) for v in variants if isinstance(v.get("inventory_level"), (int, float)))

    sku_val = data.get("sku")
    if not sku_val and isinstance(variants, list) and variants:
        sku_val = variants[0].get("sku")

    in_stock_val = data.get("in_stock")
    if in_stock_val is None and inv_val is not None:
        in_stock_val = (_safe_float(inv_val) or 0) > 0

    return {
        "product_name": _safe_str(data.get("product_name") or data.get("name")),
        "product_id": _safe_str(data.get("product_id") or data.get("id")),
        "sku": _safe_str(sku_val),
        "unit_price": _safe_float(price_val),
        "inventory_level": _safe_float(inv_val),
        "product_category": _safe_str(data.get("product_category") or data.get("category")),
        "in_stock": in_stock_val,
        "connection_id": str(record.connection_id) if record.connection_id else None,
        "provider": record.provider,
        "source_updated_at": record.source_updated_at,
    }


def _python_product_search(
    records: list[NormalizedCommerceRecord],
    *,
    product_name: str | None,
    product_id: str | None,
    sku: str | None,
) -> list[NormalizedCommerceRecord]:
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


class ProductReservationService:
    """Service gérant le cycle de vie transactionnel des réservations de produits en magasin."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def reserve_product(
        self,
        company_id: UUID,
        *,
        product_name_or_id: str,
        quantity: int = 1,
        client_name: str,
        client_phone: str | None = None,
        client_email: str | None = None,
        pickup_date: str | None = None,
        notes: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Exécute ou prépare une réservation de produit pour cueillette en magasin."""
        query_val = product_name_or_id.strip() if product_name_or_id else ""
        if not query_val:
            return {
                "success": False,
                "error": "Veuillez spécifier le nom ou l'identifiant du produit à réserver.",
            }

        # 1. Rechercher le produit dans le catalogue normalisé de l'entreprise
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
        try:
            q_term = _normalize_query(query_val)
            rows = list(
                self._session.scalars(
                    base_query.where(
                        or_(
                            NormalizedCommerceRecord.normalized_data["product_id"].astext == query_val,
                            func.lower(NormalizedCommerceRecord.normalized_data["sku"].astext) == q_term,
                            func.lower(NormalizedCommerceRecord.normalized_data["product_name"].astext).contains(q_term),
                        )
                    ).limit(5)
                ).all()
            )
            records = rows
        except Exception:
            records = []

        if not records:
            all_rows = list(self._session.scalars(base_query.limit(200)).all())
            records = _python_product_search(
                all_rows,
                product_name=query_val,
                product_id=query_val,
                sku=query_val,
            )

        if not records:
            q_norm = _normalize_query(query_val)
            all_records = list(self._session.scalars(base_query.limit(200)).all())
            scored = []
            for r in all_records:
                data = r.normalized_data or {}
                pname = str(data.get("product_name") or data.get("name") or "")
                ratio = SequenceMatcher(None, q_norm, pname.lower()).ratio()
                if ratio >= 0.5:
                    scored.append((ratio, r))
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                records = [scored[0][1]]

        if not records:
            return {
                "success": False,
                "error": f"Produit introuvable dans le catalogue : '{query_val}'.",
                "data": {"found": False, "product_query": query_val},
            }

        matched_rec = records[0]
        prod_data = _product_to_dict(matched_rec)
        pname = str(prod_data.get("product_name") or query_val)
        pid = str(prod_data.get("product_id") or "")
        sku = str(prod_data.get("sku") or "")
        price = _safe_float(prod_data.get("unit_price"))
        base_inv_level = _safe_float(prod_data.get("inventory_level"))
        in_stock = bool(prod_data.get("in_stock", False))

        # 2. Évaluer la fraîcheur de la source d'inventaire
        conn = None
        if matched_rec.connection_id:
            conn = self._session.get(CommerceConnection, matched_rec.connection_id)
        
        now = datetime.now(timezone.utc)
        is_live_conn = bool(
            conn and conn.provider in ("shopify", "woocommerce")
            and str(conn.status).upper() in ("READY", "ACTIVE", "SYNCING")
        )
        updated_at = matched_rec.source_updated_at
        if updated_at is not None and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        is_recent = bool(
            updated_at and (now - updated_at).total_seconds() < 86400
        )
        source_freshness = "LIVE" if (is_live_conn and is_recent) else "HISTORICAL_IMPORT"

        # 3. Calcul du stock net disponible en tenant compte des réservations actives (anti-double réservation)
        now = datetime.now(timezone.utc)
        active_conditions = [
            ProductReservation.company_id == company_id,
            ProductReservation.status.in_([ReservationStatus.PENDING, ReservationStatus.CONFIRMED]),
            or_(
                ProductReservation.expires_at.is_(None),
                ProductReservation.expires_at > now,
            ),
        ]
        match_conditions = []
        if pid:
            match_conditions.append(ProductReservation.product_id == pid)
        if sku:
            match_conditions.append(func.lower(ProductReservation.sku) == sku.lower())
        match_conditions.append(func.lower(ProductReservation.product_name) == pname.lower())
        
        active_holds = self._session.scalars(
            select(ProductReservation).where(
                *active_conditions,
                or_(*match_conditions),
            )
        ).all()

        reserved_quantity = sum(r.quantity for r in active_holds)
        nominal_stock = int(base_inv_level) if base_inv_level is not None else 0
        net_available_stock = max(0, nominal_stock - reserved_quantity)

        # 4. Vérification de disponibilité physique
        if (base_inv_level is not None and base_inv_level <= 0) or not in_stock:
            return {
                "success": False,
                "error": f"Le produit '{pname}' est actuellement en rupture de stock et ne peut être réservé pour cueillette immédiate.",
                "data": {
                    "found": True,
                    "product_name": pname,
                    "in_stock": False,
                    "inventory_level": 0,
                    "state": "OUT_OF_STOCK",
                },
                "source_ref": str(matched_rec.id),
            }

        if net_available_stock <= 0:
            return {
                "success": False,
                "error": f"Toutes les unités de '{pname}' ({nominal_stock} en boutique) sont actuellement réservées par d'autres clients.",
                "data": {
                    "found": True,
                    "product_name": pname,
                    "in_stock": True,
                    "nominal_stock": nominal_stock,
                    "reserved_stock": reserved_quantity,
                    "net_available_stock": 0,
                    "state": "FULLY_RESERVED",
                },
                "source_ref": str(matched_rec.id),
            }

        if quantity > net_available_stock:
            return {
                "success": False,
                "error": f"Quantité demandée ({quantity}) supérieure au stock disponible ({net_available_stock} restante(s) sur {nominal_stock}).",
                "data": {
                    "found": True,
                    "product_name": pname,
                    "requested_quantity": quantity,
                    "available_quantity": net_available_stock,
                    "nominal_stock": nominal_stock,
                    "reserved_stock": reserved_quantity,
                    "state": "INSUFFICIENT_STOCK",
                },
                "source_ref": str(matched_rec.id),
            }

        # 5. Si non confirmé, retourner la demande de confirmation explicite
        if not confirmed:
            return {
                "success": False,
                "data": {
                    "confirmation_required": True,
                    "product_name": pname,
                    "product_id": pid,
                    "sku": sku,
                    "unit_price": price,
                    "quantity": quantity,
                    "client_name": client_name,
                    "client_phone": client_phone,
                    "pickup_date": pickup_date,
                    "stock_available": net_available_stock,
                    "source_freshness": source_freshness,
                },
                "error": (
                    f"Confirmez explicitement la mise de côté en magasin de {quantity}x '{pname}' "
                    f"pour {client_name} ({pickup_date or 'date à convenir'})."
                ),
                "source_ref": str(matched_rec.id),
            }

        # 6. Génération de référence unique et statut transactionnel
        date_prefix = now.strftime("%y%m%d")
        unique_seed = f"{company_id}:{client_name}:{pname}:{time.time()}"
        code_suffix = hashlib.sha256(unique_seed.encode()).hexdigest()[:4].upper()
        reference_code = f"RES-{date_prefix}-{code_suffix}"

        # Si le stock est vérifié LIVE -> CONFIRMED
        # Si le stock provient d'un import statique CSV ou non récent -> PENDING (attente de confirmation staff)
        if source_freshness == "LIVE":
            reservation_status = ReservationStatus.CONFIRMED
            spoken_message = (
                f"Réservation confirmée sous la référence {reference_code}. "
                f"{quantity} unité(s) de '{pname}' ont été mises de côté pour {client_name}. "
                f"Cueillette prévue : {pickup_date or 'prochainement en magasin'}. "
                "Le produit est réservé en boutique ; aucun débit de stock distant n'a été effectué."
            )
        else:
            reservation_status = ReservationStatus.PENDING
            spoken_message = (
                f"Demande de réservation enregistrée sous la référence {reference_code}. "
                f"En attente de confirmation physique par l'équipe en magasin car les données de stock proviennent d'un import historique. "
                f"Notre équipe va vérifier le stock en boutique et vous recontacter."
            )

        # Expiration automatique (48h par défaut pour retrait en boutique)
        expires_at = now + timedelta(hours=48)

        # 7. Persistance effective dans la table `product_reservations`
        reservation = ProductReservation(
            id=uuid4(),
            company_id=company_id,
            reference_code=reference_code,
            status=reservation_status,
            product_id=pid or None,
            product_name=pname,
            sku=sku or None,
            quantity=quantity,
            unit_price=price,
            currency="CAD",
            client_name=client_name,
            client_phone=client_phone,
            client_email=client_email,
            pickup_date_text=pickup_date,
            notes=notes,
            source_connection_id=matched_rec.connection_id,
            source_provider=matched_rec.provider,
            source_freshness=source_freshness,
            electronic_stock_locked=False,
            expires_at=expires_at,
        )
        self._session.add(reservation)

        # Journal d'audit pour visibilité immédiate dans l'espace entreprise
        audit = AuditLogEntry(
            id=uuid4(),
            company_id=company_id,
            action="retail.reservation.created",
            target_type="product_reservation",
            target_id=str(reservation.id),
            safe_metadata={
                "actor_type": "ai_voice",
                "reference_code": reference_code,
                "status": str(reservation_status),
                "product_name": pname,
                "quantity": quantity,
                "client_name": client_name,
                "client_phone": client_phone,
                "source_freshness": source_freshness,
                "net_stock_remaining": net_available_stock - quantity,
            },
            created_at=now,
        )
        self._session.add(audit)
        self._session.flush()

        logger.info(
            "product_reservation_persisted company_id=%s ref=%s status=%s prod=%s qty=%d",
            company_id,
            reference_code,
            reservation_status,
            pname,
            quantity,
        )

        return {
            "success": True,
            "data": {
                "id": str(reservation.id),
                "reservation_id": reference_code,
                "reference_code": reference_code,
                "status": str(reservation_status),
                "reservation_type": "in_store_pickup_hold",
                "electronic_inventory_locked": False,
                "source_freshness": source_freshness,
                "product_name": pname,
                "product_id": pid,
                "sku": sku,
                "unit_price": price,
                "quantity": quantity,
                "client_name": client_name,
                "client_phone": client_phone,
                "client_email": client_email,
                "pickup_date": pickup_date,
                "expires_at": expires_at.isoformat(),
                "net_stock_remaining": net_available_stock - quantity,
                "notes": notes,
                "message": spoken_message,
            },
            "source_ref": str(matched_rec.id),
        }

    def list_reservations(
        self,
        company_id: UUID,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ProductReservation]:
        """Retourne la liste des réservations du tenant pour affichage dans l'interface commerçant."""
        query = (
            select(ProductReservation)
            .where(ProductReservation.company_id == company_id)
            .order_by(ProductReservation.created_at.desc())
            .limit(min(max(limit, 1), 200))
        )
        if status:
            query = query.where(ProductReservation.status == str(status).upper())
        return list(self._session.scalars(query).all())

    def update_reservation_status(
        self,
        company_id: UUID,
        reservation_id_or_code: str,
        *,
        new_status: str,
        reason: str | None = None,
    ) -> ProductReservation:
        """Permet au commerçant de changer l'état d'une réservation (ex: COLLECTED, CANCELLED)."""
        st = str(new_status).upper()
        if st not in ReservationStatus.__members__:
            raise ValueError(f"Statut de réservation invalide : {new_status}")

        query = select(ProductReservation).where(ProductReservation.company_id == company_id)
        try:
            res_uuid = UUID(reservation_id_or_code)
            query = query.where(or_(ProductReservation.id == res_uuid, ProductReservation.reference_code == reservation_id_or_code))
        except ValueError:
            query = query.where(ProductReservation.reference_code == reservation_id_or_code)

        res = self._session.scalar(query)
        if res is None:
            raise LookupError(f"Réservation introuvable : {reservation_id_or_code}")

        res.status = st
        now = datetime.now(timezone.utc)
        if st == ReservationStatus.COLLECTED:
            res.collected_at = now
        elif st == ReservationStatus.CANCELLED:
            res.cancelled_at = now
            res.cancellation_reason = reason

        self._session.flush()
        return res
