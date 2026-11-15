"""Trading crypto en direct, inclus dans Base et Professional."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.permission_grants import effective_permissions
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.services.crypto_market import MarketUnavailable, candles, popular, quotes, search
from backend.app.services.trading_engine import add_watch, list_watch, remove_watch

router = APIRouter(prefix="/trading", tags=["trading"])


class WatchRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)


def require_trading(
    identity: CurrentIdentity = Depends(get_current_identity),
) -> CurrentIdentity:
    if "trading:read" not in effective_permissions(identity.user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission insuffisante")
    return identity


def _market_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (KeyError, ValueError)):
        return HTTPException(status_code=404, detail="Crypto introuvable")
    return HTTPException(status_code=503, detail="Cours Binance indisponible")


@router.get("/status")
def trading_status(identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    return {
        "data_mode": "live",
        "realtime": True,
        "source": "binance-public",
        "included_in": ["base", "professional"],
        "extra_plan": False,
        "brokerage": False,
        "advice": False,
        "message": "Cours crypto publics Binance, inclus dans Base et Professional. Aucun ordre et aucun conseil.",
    }


@router.get("/instruments")
def trading_instruments(q: str = "", identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    try:
        instruments = search(q) if q else popular()
    except MarketUnavailable as exc:
        raise _market_error(exc) from exc
    return {"data_mode": "live", "source": "binance-public", "instruments": instruments}


@router.get("/candles")
def trading_candles(
    symbol: str,
    interval: str = "1m",
    identity: CurrentIdentity = Depends(require_trading),
) -> dict:
    del identity
    try:
        return candles(symbol, interval)
    except (KeyError, ValueError, MarketUnavailable) as exc:
        raise _market_error(exc) from exc


@router.get("/quotes")
def trading_quotes(symbols: str = "", identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    requested = [item for item in symbols.split(",") if item.strip()]
    try:
        return quotes(requested)
    except (KeyError, ValueError, MarketUnavailable) as exc:
        raise _market_error(exc) from exc


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
