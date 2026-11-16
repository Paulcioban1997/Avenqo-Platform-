"""Outils d'intelligence de marché et Trading AI autorisés pour Central AI et Voice.

Règles de conformité et d'intégrité financière (P0) :
1. Aucun cours fictif : si le flux de marché est hors ligne, le statut est "unavailable", jamais un faux prix.
2. Aucune cotation boursière non agréée : les actions (AAPL, TSLA, etc.) ne disposant pas de flux temps réel
   réglementé sont explicitement déclarées non prises en charge.
3. Prédictions désactivées par défaut : aucun chiffre spéculatif fictif n'est formulé tant que les modèles
   (GRU, XGBoost, Transformer) n'ont pas fait l'objet d'évaluations certifiées en production.
4. Aucun ratio de risque inventé : Sharpe Ratio, Win Rate et Drawdown exigent un historique de transactions
   audité, sans substitut synthétique silencieux.
5. Isolation multi-tenant et vérification des habilitations 'trading:read' et entitlements à chaque appel.
"""
from __future__ import annotations

import re
from typing import Any
from pydantic import Field
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import TradingAITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.services.market_feed import factual_brief, live_quote, MarketUnavailable
from backend.app.services.module_entitlement_service import ModuleEntitlementService

_KNOWN_EQUITY_SYMBOLS = frozenset({
    "AAPL", "TSLA", "MSFT", "GOOG", "GOOGL", "AMZN", "NVDA", "META", "SPY", "QQQ"
})


class AssetQuoteArgs(ToolArguments):
    symbol: str = Field(
        default="BTC/USD",
        description="Symbole crypto vérifié à interroger (ex: BTC/USD, ETH/USD, SOL/USD).",
        min_length=1,
        max_length=32,
    )


class TradingPredictionArgs(ToolArguments):
    symbol: str = Field(
        default="BTC/USD",
        description="Symbole crypto pour lequel interroger les prédictions certifiées.",
        min_length=1,
        max_length=32,
    )
    horizon: str = Field(
        default="24h",
        description="Horizon temporel prédictif ('1h', '24h', '7d', '30d').",
    )


class TradingRiskArgs(ToolArguments):
    symbol: str = Field(
        default="BTC/USD",
        description="Symbole pour l'analyse de risque de portefeuille audité.",
        min_length=1,
        max_length=32,
    )


def _normalize_crypto_symbol(raw: str) -> str:
    cleaned = raw.strip().upper().replace(" ", "").replace("_", "")
    if "/" not in cleaned and "-" not in cleaned:
        if cleaned.endswith("USDT") and len(cleaned) > 4:
            return f"{cleaned[:-4]}/USDT"
        if cleaned.endswith("USD") and len(cleaned) > 3:
            return f"{cleaned[:-3]}/USD"
        if cleaned.endswith("EUR") and len(cleaned) > 3:
            return f"{cleaned[:-3]}/EUR"
        return f"{cleaned}/USD"
    return cleaned.replace("-", "/")


class GetTradingAssetQuoteTool(TradingAITool):
    """Fournit les cotations de marché en temps réel et l'évolution 24h d'un actif vérifié."""

    name = "get_asset_quote"
    description = (
        "Consulte le cours actuel, l'évolution récente et la fraîcheur d'un actif crypto vérifié. "
        "Usage strictement informatif, aucune exécution d'ordre de bourse."
    )
    input_schema = AssetQuoteArgs
    required_permissions = ("ai:use", "trading:read")

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def execute(self, asset: str = "BTC") -> dict[str, Any]:
        raw_sym = asset.strip().upper()
        # 1. Vérification des actions traditionnelles (actions US/internationales sans flux agréé)
        base_token = re.split(r"[/_\-\s]", raw_sym)[0]
        if base_token in _KNOWN_EQUITY_SYMBOLS or raw_sym in _KNOWN_EQUITY_SYMBOLS:
            return {
                "status": "unsupported_asset",
                "asset": raw_sym,
                "symbol": raw_sym,
                "price_usd": None,
                "freshness": "unavailable",
                "error": (
                    f"Les cotations d'actions (actions américaines telles que {raw_sym}) "
                    "nécessitent une intégration de courtage agréée non connectée sur cet environnement. "
                    "Seules les paires cryptographiques vérifiées sont actuellement disponibles."
                ),
                "vocal_summary": (
                    f"Les cotations pour l'action {raw_sym} nécessitent un flux boursier agréé "
                    "non disponible sur ce serveur. Seules les cryptomonnaies sont prises en charge."
                ),
            }

        # 2. Normalisation du symbole crypto
        sym = _normalize_crypto_symbol(raw_sym)

        # 3. Récupération auprès du flux de marché réel (sans données fictives)
        try:
            quote_data = live_quote(sym)
            price = quote_data.get("price")
            if price is None:
                raise MarketUnavailable(f"Prix absent pour {sym}")

            freshness = str(quote_data.get("freshness", "stale"))
            change_24h = quote_data.get("change_percent_24h")
            high_24h = quote_data.get("high_24h")
            low_24h = quote_data.get("low_24h")

            # Synthèse textuelle
            summary_text = ""
            try:
                brief = factual_brief(sym, interval="1h", locale="fr")
                summary_text = str(brief.get("text", ""))
            except Exception:
                summary_text = f"Cours vérifié {sym} à {price:,.2f} USD."

            return {
                "status": "success",
                "asset": base_token,
                "symbol": sym,
                "price_usd": float(price),
                "change_24h": change_24h,
                "high_24h": high_24h,
                "low_24h": low_24h,
                "freshness": freshness,
                "source": quote_data.get("source"),
                "updated_at": quote_data.get("updated_at"),
                "analysis_summary": summary_text,
                "vocal_summary": (
                    f"Le cours en direct de {base_token} est de {price:,.2f} USD ({freshness})."
                    if freshness == "realtime"
                    else f"Le dernier cours enregistré pour {base_token} est de {price:,.2f} USD (données différées)."
                ),
            }
        except (MarketUnavailable, ValueError, KeyError) as exc:
            return {
                "status": "unavailable",
                "asset": base_token,
                "symbol": sym,
                "price_usd": None,
                "freshness": "unavailable",
                "error": f"Le flux de marché pour {sym} est temporairement indisponible. Aucun cours fictif n'est retourné ({exc}).",
                "vocal_summary": f"Désolé, le flux de marché pour {base_token} est actuellement indisponible.",
            }

    async def run(self, context: ToolExecutionContext, arguments: AssetQuoteArgs) -> ToolResult:
        if "trading:read" not in context.permissions:
            return ToolResult(
                success=False,
                error="Permission 'trading:read' requise pour accéder aux cotations financières.",
            )
        if self._session is not None:
            entitlements = ModuleEntitlementService(self._session)
            if not entitlements.can_use_module(context.tenant, "trading"):
                return ToolResult(
                    success=False,
                    error="Le module Trading AI n'est pas activé pour cette entreprise.",
                )
        data = self.execute(arguments.symbol)
        if data.get("status") == "success":
            return ToolResult(success=True, data=data)
        return ToolResult(success=False, error=data.get("error", "Cours indisponible"), data=data)


class GetTradingPredictionsTool(TradingAITool):
    """Fournit les prévisions des modèles d'apprentissage automatique validés (GRU, XGBoost, Transformer)."""

    name = "get_trading_predictions"
    description = (
        "Consulte les prévisions de prix calculées par les modèles prédictifs certifiés Avenqo Trading. "
        "Désactivé tant que des modèles certifiés et audités ne sont pas en production."
    )
    input_schema = TradingPredictionArgs
    required_permissions = ("ai:use", "trading:read")

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def execute(self, asset: str = "BTC", horizon: str = "24h") -> dict[str, Any]:
        # Conformité stricte : aucun modèle synthétique demo ou chiffre aléatoire
        raw_sym = asset.strip().upper()
        sym = _normalize_crypto_symbol(raw_sym)
        return {
            "status": "unavailable",
            "asset": raw_sym,
            "symbol": sym,
            "horizon": horizon,
            "predicted_price": None,
            "direction": None,
            "confidence": None,
            "models": {},
            "error": (
                "Les modèles prédictifs d'apprentissage profond (GRU, XGBoost, Transformer) "
                "ne disposent pas encore d'évaluations certifiées en production pour cet actif. "
                "Conformément aux règles d'intégrité financière Avenqo, aucune prédiction fictive n'est diffusée."
            ),
            "vocal_summary": (
                f"Les modèles prédictifs pour {raw_sym} ne sont pas encore certifiés en production. "
                "Aucune prédiction spéculative ne peut être formulée."
            ),
        }

    async def run(self, context: ToolExecutionContext, arguments: TradingPredictionArgs) -> ToolResult:
        if "trading:read" not in context.permissions:
            return ToolResult(
                success=False,
                error="Permission 'trading:read' requise pour accéder aux prédictions.",
            )
        if self._session is not None:
            entitlements = ModuleEntitlementService(self._session)
            if not entitlements.can_use_module(context.tenant, "trading"):
                return ToolResult(
                    success=False,
                    error="Le module Trading AI n'est pas activé pour cette entreprise.",
                )
        data = self.execute(arguments.symbol, arguments.horizon)
        return ToolResult(
            success=False,
            error=data["error"],
            data=data,
        )


class GetTradingPortfolioRiskTool(TradingAITool):
    """Fournit l'évaluation du risque de portefeuille et les métriques de simulation Strategy Lab."""

    name = "get_trading_portfolio_risk"
    description = (
        "Calcule les indicateurs techniques et les métriques de risque du Strategy Lab "
        "(Sharpe ratio, Max Drawdown, Win Rate) à partir de transactions réelles auditées."
    )
    input_schema = TradingRiskArgs
    required_permissions = ("ai:use", "trading:read")

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def execute(self, asset: str = "BTC") -> dict[str, Any]:
        # Conformité stricte : aucun Sharpe ou Win Rate inventé
        raw_sym = asset.strip().upper()
        return {
            "status": "unavailable",
            "asset": raw_sym,
            "portfolio_risk_level": "UNKNOWN",
            "sharpe_ratio": None,
            "max_drawdown": None,
            "win_rate": None,
            "benchmark_return": None,
            "strategy_return": None,
            "error": (
                "Aucune simulation validée ni historique de transaction audité n'est disponible "
                "pour calculer le ratio de Sharpe, le Win Rate ou le risque de portefeuille. "
                "Aucune métrique financière fictive n'est affichée."
            ),
            "vocal_summary": (
                "Aucun historique de trading vérifié n'est disponible pour calculer les métriques de risque de ce portefeuille."
            ),
        }

    async def run(self, context: ToolExecutionContext, arguments: TradingRiskArgs) -> ToolResult:
        if "trading:read" not in context.permissions:
            return ToolResult(
                success=False,
                error="Permission 'trading:read' requise pour accéder aux métriques de risque.",
            )
        if self._session is not None:
            entitlements = ModuleEntitlementService(self._session)
            if not entitlements.can_use_module(context.tenant, "trading"):
                return ToolResult(
                    success=False,
                    error="Le module Trading AI n'est pas activé pour cette entreprise.",
                )
        data = self.execute(arguments.symbol)
        return ToolResult(
            success=False,
            error=data["error"],
            data=data,
        )
