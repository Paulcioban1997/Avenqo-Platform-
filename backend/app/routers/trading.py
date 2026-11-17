"""Trading crypto public, module optionnel dans la limite du forfait."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.core.permission_grants import effective_permissions
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.services.fx_rates import convert_amount
from backend.app.services.market_feed import (
    MarketUnavailable,
    asset_classes,
    calculate_backtest,
    candles,
    experimental_study,
    factual_brief,
    popular,
    quotes,
    rankings,
    search,
)
from backend.app.services.market_stream import stream_health as socket_health
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.trading_engine import add_watch, list_watch, remove_watch
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/trading", tags=["trading"])


class WatchRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)


class AskRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    compare: str | None = Field(default=None, max_length=32)
    interval: str = "1h"
    locale: str = "fr"
    question: str | None = Field(default=None, max_length=1000)


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    interval: str = "1h"
    strategy: str = "crossover_sma"
    fast_period: int = Field(default=10, ge=2, le=100)
    slow_period: int = Field(default=30, ge=3, le=200)
    fee_rate: float = Field(default=0.001, ge=0.0, le=0.05)
    slippage_rate: float = Field(default=0.0005, ge=0.0, le=0.05)
    candle_limit: int = Field(default=200, ge=50, le=500)


def require_trading(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> CurrentIdentity:
    if "trading:read" not in effective_permissions(identity.user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission insuffisante")
    tenant = TenantContext(identity.user.company_id)
    if not ModuleEntitlementService(db).can_use_module(tenant, "trading"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Module Trading non activé")
    return identity


def _market_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (KeyError, ValueError)):
        return HTTPException(status_code=404, detail="Crypto introuvable")
    return HTTPException(status_code=503, detail="Cours public indisponible")


@router.get("/status")
def trading_status(identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    return {
        "data_mode": "public",
        "extra_plan": False,
        "counts_as_module": True,
        "brokerage": False,
        "advice": False,
        "providers": ["binance-public", "coinbase-public"],
        "streams": socket_health(),
        "asset_classes": asset_classes()["classes"],
        "message": "Module optionnel. Cours publics Binance et Coinbase. Aucun ordre et aucun conseil.",
    }


@router.get("/instruments")
def trading_instruments(
    q: str = "",
    quote: str = "USDT",
    identity: CurrentIdentity = Depends(require_trading),
) -> dict:
    del identity
    try:
        instruments = search(q, quote) if q else popular(quote)
    except (MarketUnavailable, ValueError) as exc:
        raise _market_error(exc) from exc
    return {"instruments": instruments, "quote": quote.upper()}


@router.get("/candles")
def trading_candles(
    symbol: str,
    interval: str = "1m",
    provider: str = "auto",
    identity: CurrentIdentity = Depends(require_trading),
) -> dict:
    del identity
    try:
        return candles(symbol, interval, provider=provider)
    except (KeyError, ValueError, MarketUnavailable) as exc:
        raise _market_error(exc) from exc


@router.get("/quotes")
def trading_quotes(
    symbols: str = "",
    provider: str = "auto",
    display: str = "",
    identity: CurrentIdentity = Depends(require_trading),
) -> dict:
    requested = [item for item in symbols.split(",") if item.strip()]
    try:
        payload = quotes(requested, provider)
    except (KeyError, ValueError, MarketUnavailable) as exc:
        raise _market_error(exc) from exc
    target = (display or getattr(identity.user.company, "display_currency", None) or "").upper()
    payload["display_currency"] = target or None
    if target:
        for row in payload["quotes"]:
            row["display"] = convert_amount(row["price"], row.get("currency") or "USDT", target)
    return payload


@router.get("/rankings")
def trading_rankings(identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    try:
        return rankings()
    except MarketUnavailable as exc:
        return {
            "source": "binance-public",
            "transport": "rest",
            "freshness": "unavailable",
            "currency": "USDT",
            "rows": [],
            "error": str(exc),
        }


@router.get("/asset-classes")
def trading_asset_classes(identity: CurrentIdentity = Depends(require_trading)) -> dict:
    del identity
    return asset_classes()


async def _explain_with_gemini(
    question: str,
    brief: dict,
    symbol: str,
    interval: str,
    locale: str,
    settings: Settings,
) -> str:
    if not settings.google_ai_api_key:
        return brief.get("text", "")

    indicators = brief.get("indicators", {})
    source = brief.get("source", "Binance/Coinbase")
    freshness = brief.get("freshness", "delayed")
    change = brief.get("change_percent", 0.0)

    system_instruction = (
        "Tu es l'analyste quantitatif de marché et assistant financier Avenqo Trading AI. "
        "RÈGLES STRICTES :\n"
        "1. N'invente AUCUN prix, aucun faux Sharpe ratio ni fausse statistique. Fonde-toi exclusivement sur les métriques factuelles fournies.\n"
        "2. Explique avec clarté technique les concepts (RSI, MACD, moyennes mobiles, volatilité, supports/résistances).\n"
        "3. Rappelle qu'Avenqo ne fournit pas de conseil en investissement ni d'ordres automatisés.\n"
        f"4. Réponds dans la langue demandée ({locale})."
    )

    prompt = (
        f"Actif : {symbol}\n"
        f"Intervalle : {interval}\n"
        f"Source : {source} ({freshness})\n"
        f"Variation : {change:.2f}%\n"
        f"Indicateurs :\n"
        f"- SMA 20 : {indicators.get('sma_20')}\n"
        f"- EMA 12 : {indicators.get('ema_12')}\n"
        f"- RSI 14 : {indicators.get('rsi_14')}\n"
        f"- MACD Histogramme : {indicators.get('macd', {}).get('histogram')}\n"
        f"- Bandes de Bollinger : {indicators.get('bollinger', {}).get('middle')} "
        f"(haute: {indicators.get('bollinger', {}).get('upper')}, basse: {indicators.get('bollinger', {}).get('lower')})\n\n"
        f"Question : {question}\n"
    )

    try:
        from backend.app.ai.llm.gemini_provider import GeminiProvider

        model_name = settings.gemini_model or "gemini-2.5-flash"
        provider = GeminiProvider(
            api_key=settings.google_ai_api_key,
            model=model_name,
            temperature=0.2,
            max_tokens=600,
            request_timeout_seconds=10.0,
        )
        generation = await provider.generate(system_instruction=system_instruction, prompt=prompt)
        if generation.content and generation.content.strip():
            return generation.content.strip()
    except Exception:
        pass
    return brief.get("text", "")


@router.post("/ask")
async def trading_ask(
    payload: AskRequest,
    identity: CurrentIdentity = Depends(require_trading),
    settings: Settings = Depends(get_settings),
) -> dict:
    del identity
    try:
        brief = factual_brief(payload.symbol, payload.interval, payload.compare, payload.locale)
        series = candles(payload.symbol, payload.interval, 200)
        brief["study"] = experimental_study([row["close"] for row in series["candles"]])
        if payload.question and payload.question.strip():
            brief["text"] = await _explain_with_gemini(
                payload.question.strip(),
                brief,
                payload.symbol,
                payload.interval,
                payload.locale,
                settings,
            )
        return brief
    except (KeyError, ValueError, MarketUnavailable) as exc:
        raise _market_error(exc) from exc


@router.post("/backtest")
def trading_backtest(
    payload: BacktestRequest,
    identity: CurrentIdentity = Depends(require_trading),
) -> dict:
    del identity
    if payload.fast_period >= payload.slow_period:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"fast_period ({payload.fast_period}) doit être strictement inférieur à slow_period ({payload.slow_period})",
        )
    if payload.strategy not in ("crossover_sma", "crossover_ema"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stratégie non supportée: '{payload.strategy}'. Valeurs autorisées: crossover_sma, crossover_ema",
        )
    supported_intervals = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "1j", "1w")
    if payload.interval not in supported_intervals:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Intervalle non supporté: '{payload.interval}'. Valeurs autorisées: {', '.join(supported_intervals)}",
        )
    try:
        query_interval = "1d" if payload.interval == "1j" else payload.interval
        series = candles(payload.symbol, query_interval, payload.candle_limit)
        candle_list = series.get("candles") or []
        closes = [
            float(row["close"])
            for row in candle_list
            if isinstance(row, dict) and "close" in row and isinstance(row["close"], (int, float)) and row["close"] > 0
        ]
        result = calculate_backtest(
            closes=closes,
            strategy=payload.strategy,
            fast_period=payload.fast_period,
            slow_period=payload.slow_period,
            fee_rate=payload.fee_rate,
            slippage_rate=payload.slippage_rate,
            interval=payload.interval,
        )
        result["symbol"] = payload.symbol
        result["interval"] = payload.interval
        result["freshness"] = series.get("freshness", "delayed")
        result["source"] = series.get("source", "public")
        return result
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
        raise HTTPException(status_code=404, detail="Crypto introuvable") from exc
    return {"symbols": symbols}


@router.delete("/watchlist/{symbol}")
def trading_watch_remove(
    symbol: str,
    identity: CurrentIdentity = Depends(require_trading),
    db: Session = Depends(get_db),
) -> dict:
    return {"symbols": remove_watch(db, identity.user.company_id, identity.user.id, symbol.strip().upper())}
