"""Trading crypto public, module optionnel dans la limite du forfait."""

import math
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


class ChatMessage(BaseModel):
    role: str = Field(description="'user' ou 'assistant'")
    content: str = Field(max_length=2000)


class AskRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    compare: str | None = Field(default=None, max_length=32)
    interval: str = "1h"
    locale: str = "fr"
    question: str | None = Field(default=None, max_length=1000)
    conversation_history: list[ChatMessage] = Field(default_factory=list)


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


def _synthesize_fluid_trading_analysis(
    question: str,
    brief: dict,
    symbol: str,
    interval: str,
    locale: str,
) -> str:
    indicators = brief.get("indicators") or {}
    rsi = indicators.get("rsi_14")
    macd = indicators.get("macd") or {}
    hist = macd.get("histogram")
    bollinger = indicators.get("bollinger") or {}
    b_mid = bollinger.get("middle")
    b_up = bollinger.get("upper")
    b_low = bollinger.get("lower")
    sma20 = indicators.get("sma_20")
    ema12 = indicators.get("ema_12")
    change = brief.get("change_percent", 0.0)

    # RSI diagnostic
    if rsi is not None and isinstance(rsi, (int, float)):
        if rsi >= 70:
            rsi_desc = f"**RSI 14 ({rsi:.1f})** : Zone de surachat. La dynamique acheteuse a été vigoureuse, signalant une surchauffe technique et un risque de consolidation ou de retour vers la moyenne."
        elif rsi <= 30:
            rsi_desc = f"**RSI 14 ({rsi:.1f})** : Zone de survente prononcée. Le flux vendeur domine actuellement, ouvrant la voie à une potentielle réaction technique ou absorption."
        elif rsi >= 50:
            rsi_desc = f"**RSI 14 ({rsi:.1f})** : Momentum modérément haussier, au-dessus du niveau pivot des 50 sans excès critique."
        else:
            rsi_desc = f"**RSI 14 ({rsi:.1f})** : Pression vendeuse sous le niveau médian 50, traduisant une dynamique encore hésitante."
    else:
        rsi_desc = "RSI 14 en cours de stabilisation."

    # MACD momentum diagnostic
    if hist is not None and isinstance(hist, (int, float)):
        if hist > 0:
            macd_desc = f"**MACD Histogramme ({hist:+.2f})** : Accélération haussière du momentum. L'écartement favorise les acheteurs sur l'intervalle {interval}."
        else:
            macd_desc = f"**MACD Histogramme ({hist:+.2f})** : Momentum baissier actif. La pression court terme demeure orientée à la baisse."
    else:
        macd_desc = "MACD en consolidation neutre."

    # Bollinger Bands diagnostic
    if b_mid and b_up and b_low and isinstance(b_mid, (int, float)) and b_mid > 0:
        width = ((float(b_up) - float(b_low)) / float(b_mid)) * 100
        if width < 3.0:
            vol_desc = f"**Bandes de Bollinger (largeur {width:.1f}%)** : Forte contraction de volatilité (Squeeze). Une sortie de range explosive est historiquement fréquente suite à cette compression."
        else:
            vol_desc = f"**Bandes de Bollinger** : Canal ouvert ({float(b_low):,.2f} - {float(b_up):,.2f}), volatilité active de {width:.1f}%."
    else:
        vol_desc = "Bandes de Bollinger calculées sur la série disponible."

    # Moving average trend
    if ema12 and sma20 and isinstance(ema12, (int, float)) and isinstance(sma20, (int, float)):
        if ema12 > sma20:
            ma_desc = f"**Moyennes mobiles** : L'EMA 12 ({float(ema12):,.2f}) se maintient au-dessus de la SMA 20 ({float(sma20):,.2f}), confirmant une structure ascendante."
        else:
            ma_desc = f"**Moyennes mobiles** : L'EMA 12 ({float(ema12):,.2f}) est sous la SMA 20 ({float(sma20):,.2f}), formant une résistance dynamique."
    else:
        ma_desc = "Moyennes mobiles en cours d'actualisation."

    is_french = locale.lower().startswith("fr")
    if is_french:
        return (
            f"**Analyse technique en direct · {symbol} ({interval})**\n\n"
            f"En réponse à votre question sur *« {question} »* :\n\n"
            f"- {rsi_desc}\n"
            f"- {macd_desc}\n"
            f"- {vol_desc}\n"
            f"- {ma_desc}\n\n"
            f"💡 **Lecture de marché :** Avec une variation de {change:+.2f}% sur la période, le positionnement nécessite de surveiller précisément les niveaux d'invalidation et de respecter une stricte discipline de gestion du risque.\n\n"
            f"*Avenqo Trading AI — Données factuelles de marché issues de sources publiques. Ne constitue pas un conseil financier.*"
        )
    return (
        f"**Live Technical Analysis · {symbol} ({interval})**\n\n"
        f"Regarding your query *\"{question}\"*:\n\n"
        f"- {rsi_desc}\n"
        f"- {macd_desc}\n"
        f"- {vol_desc}\n"
        f"- {ma_desc}\n\n"
        f"💡 **Market Context:** At {change:+.2f}% over the period, technical positioning requires monitoring invalidation levels and applying disciplined risk management.\n\n"
        f"*Avenqo Trading AI — Factual market data. Not financial advice.*"
    )


async def _explain_with_gemini(
    question: str,
    brief: dict,
    symbol: str,
    interval: str,
    locale: str,
    settings: Settings,
    conversation_history: list[ChatMessage] | None = None,
) -> str:
    indicators = brief.get("indicators", {})
    source = brief.get("source", "Binance/Coinbase")
    freshness = brief.get("freshness", "delayed")
    change = brief.get("change_percent", 0.0)

    fallback_analysis = _synthesize_fluid_trading_analysis(
        question=question,
        brief=brief,
        symbol=symbol,
        interval=interval,
        locale=locale,
    )

    if not settings.google_ai_api_key:
        return fallback_analysis

    system_instruction = (
        "Tu es l'analyste quantitatif de marché et mentor trading d'Avenqo Trading AI. "
        "Ton rôle est d'avoir une conversation fluide, naturelle, vivante et hautement experte en trading "
        "avec l'utilisateur.\n\n"
        "DIRECTIVES STRICTES :\n"
        "1. Adopte un ton direct, professionnel et pédagogique, comme un trader institutionnel chevronné qui échange en salle de marché.\n"
        "2. Analyse avec précision les indicateurs réels transmis (RSI 14, histogramme MACD, SMA 20, EMA 12/26, Bandes de Bollinger, variation).\n"
        "3. Réponds spécifiquement à la question posée : décris la dynamique de marché, la volatilité (compression vs expansion), le momentum, les confluences et les niveaux clés d'invalidation.\n"
        "4. N'invente AUCUN cours fictif ni garantie de gain futur. Reste factuel, probabiliste et rigoureux.\n"
        "5. Intègre le contexte des messages précédents pour maintenir une conversation continue et naturelle.\n"
        "6. Structure ta réponse avec clarté (notations en gras, puces de synthèse).\n"
        "7. Rappelle brièvement qu'il s'agit d'une lecture technique objective et non d'une incitation financière.\n"
        f"8. Réponds impérativement dans la langue demandée ({locale})."
    )

    history_section = ""
    if conversation_history:
        formatted_history = []
        for msg in conversation_history[-6:]:
            role = "Trader" if msg.role == "user" else "Avenqo AI"
            formatted_history.append(f"{role}: {msg.content}")
        history_section = "Historique récent de l'échange :\n" + "\n".join(formatted_history) + "\n\n"

    prompt = (
        f"Actif analysé : {symbol}\n"
        f"Unité de temps : {interval}\n"
        f"Source flux : {source} ({freshness})\n"
        f"Variation sur la période : {change:+.2f}%\n"
        f"Indicateurs techniques calculés :\n"
        f"  - SMA 20 : {indicators.get('sma_20')}\n"
        f"  - EMA 12 : {indicators.get('ema_12')}\n"
        f"  - EMA 26 : {indicators.get('ema_26')}\n"
        f"  - RSI 14 : {indicators.get('rsi_14')}\n"
        f"  - MACD Histogramme : {indicators.get('macd', {}).get('histogram')}\n"
        f"  - MACD Ligne / Signal : {indicators.get('macd', {}).get('line')} / {indicators.get('macd', {}).get('signal')}\n"
        f"  - Bandes de Bollinger : médiane {indicators.get('bollinger', {}).get('middle')}, "
        f"haute {indicators.get('bollinger', {}).get('upper')}, basse {indicators.get('bollinger', {}).get('lower')}\n\n"
        f"{history_section}"
        f"Question du trader : {question}\n"
    )

    try:
        from backend.app.ai.llm.gemini_provider import GeminiProvider

        model_name = settings.gemini_model or "gemini-2.5-flash"
        provider = GeminiProvider(
            api_key=settings.google_ai_api_key,
            model=model_name,
            temperature=0.3,
            max_tokens=800,
            request_timeout_seconds=12.0,
        )
        generation = await provider.generate(system_instruction=system_instruction, prompt=prompt)
        if generation.content and generation.content.strip():
            return generation.content.strip()
    except Exception:
        pass
    return fallback_analysis


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
                conversation_history=payload.conversation_history,
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
        closes: list[float] = []
        corrupted = False
        for row in candle_list:
            if not isinstance(row, dict) or "close" not in row or not isinstance(row["close"], (int, float)) or not math.isfinite(row["close"]) or row["close"] <= 0:
                corrupted = True
                break
            closes.append(float(row["close"]))

        if corrupted:
            return {
                "status": "invalid_series",
                "reliable": False,
                "symbol": payload.symbol,
                "interval": payload.interval,
                "strategy": payload.strategy,
                "fast_period": payload.fast_period,
                "slow_period": payload.slow_period,
                "data_integrity": {
                    "status": "rejected",
                    "continuous": False,
                    "reason": "Série temporelle corrompue ou interrompue (cours manquant, non-fini ou négatif). Rejetée pour préserver l'intégrité chronologique.",
                },
                "execution": {
                    "status": "rejected",
                    "strategy": payload.strategy,
                },
                "statistical_validation": {
                    "status": "rejected",
                    "certified_strategy": False,
                },
                "candles_count": len(candle_list),
                "trades_count": 0,
                "closed_trades_count": 0,
                "open_position": None,
                "strategy_return": None,
                "holding_return": None,
                "max_drawdown": None,
                "win_rate": None,
                "sharpe_ratio": None,
                "freshness": series.get("freshness", "delayed"),
                "source": series.get("source", "public"),
                "disclaimer": "Calcul impossible : série chronologique rejetée pour préserver l'intégrité temporelle.",
            }

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
