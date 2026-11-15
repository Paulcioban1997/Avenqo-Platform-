"""Trading AI. Demo series only until a licensed feed is configured."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.permission_grants import effective_permissions
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.trading_engine import (
    DEMO_INSTRUMENTS,
    DEMO_SOURCE,
    add_watch,
    candles,
    forecast,
    instrument,
    list_watch,
    remove_watch,
    simulation,
)
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/trading", tags=["trading"])


class WatchRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)


def require_trading(
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> CurrentIdentity:
    if "trading:read" not in effective_permissions(identity.user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission insuffisante")
    if not ModuleEntitlementService(db).can_use_module(tenant, "trading"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Module trading inactif")
    return identity


@router.get("/status")
def trading_status(identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    return {
        "data_mode": "demo",
        "realtime": False,
        "source": DEMO_SOURCE,
        "live_provider": None,
        "brokerage": False,
        "advice": False,
        "message": "Données synthétiques. Aucune cote réelle, aucun ordre, aucun conseil d'achat ou de vente.",
    }


@router.get("/instruments")
def trading_instruments(identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    return {"data_mode": "demo", "source": DEMO_SOURCE, "instruments": list(DEMO_INSTRUMENTS)}


@router.get("/candles")
def trading_candles(symbol: str, identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    try:
        return candles(symbol)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Instrument démo introuvable") from exc


@router.get("/forecast")
def trading_forecast(symbol: str, horizon: str = "7d", identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    if instrument(symbol) is None:
        raise HTTPException(status_code=404, detail="Instrument démo introuvable")
    try:
        return forecast(symbol, horizon)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="Horizon non pris en charge") from exc


@router.get("/simulation")
def trading_simulation(symbol: str, identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    try:
        return simulation(symbol)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Instrument démo introuvable") from exc


@router.get("/watchlist")
def trading_watchlist(
    identity: CurrentIdentity = Depends(require_trading),
    db: Session = Depends(get_db),
) -> dict:
    return {"symbols": list_watch(db, identity.user.company_id, identity.user.id)}


@router.post("/watchlist")
def trading_watch_add(
    payload: WatchRequest,
    identity: CurrentIdentity = Depends(require_trading),
    db: Session = Depends(get_db),
) -> dict:
    try:
        symbols = add_watch(db, identity.user.company_id, identity.user.id, payload.symbol.strip().upper())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Instrument démo introuvable") from exc
    return {"symbols": symbols}


@router.delete("/watchlist/{symbol}")
def trading_watch_remove(
    symbol: str,
    identity: CurrentIdentity = Depends(require_trading),
    db: Session = Depends(get_db),
) -> dict:
    return {"symbols": remove_watch(db, identity.user.company_id, identity.user.id, symbol.strip().upper())}
