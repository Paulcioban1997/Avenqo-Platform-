"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api-request";
import { TRADING_COPY } from "@/lib/i18n/trading-copy";
import type { LocaleCode } from "@/lib/i18n/types";

interface ModelItem {
  name: string;
  horizon: string;
  precision: number | null;
  directionAccuracy: number | null;
  status: "evaluating" | "training" | "certified";
}

interface BacktestData {
  status: string;
  reliable: boolean;
  candles_count: number;
  evaluation_candles?: number;
  trades_count: number;
  closed_trades_count?: number;
  strategy_return: number | null;
  holding_return: number | null;
  max_drawdown: number | null;
  win_rate: number | null;
  sharpe_ratio: number | null;
  open_position?: {
    entry_price: number;
    entry_bar: number;
    current_price: number;
    unrealized_return: number;
    bars_held: number;
  } | null;
  assumptions?: {
    fee_rate: number;
    fee_rate_percent: number;
    slippage_rate: number;
    slippage_rate_percent: number;
    annual_bars: number;
    annual_factor: number;
    interval: string;
  };
  disclaimer: string;
}

interface TradingModelsCardProps {
  symbol?: string;
  interval?: string;
  locale: LocaleCode;
}

export function TradingModelsCard({
  symbol = "BTCUSDT",
  interval = "1h",
  locale,
}: TradingModelsCardProps) {
  const copy = TRADING_COPY[locale] || TRADING_COPY.fr;
  const [runningBacktest, setRunningBacktest] = useState(false);
  const [backtestResult, setBacktestResult] = useState<BacktestData | null>(null);
  const [backtestError, setBacktestError] = useState("");

  // Modèles quantitatifs en cours d'évaluation hors-échantillon (aucun chiffre inventé)
  const models: ModelItem[] = [
    { name: "Tendance Court Terme (Intraday)", horizon: "1h", precision: null, directionAccuracy: null, status: "evaluating" },
    { name: "Analyse Séquentielle (Swing)", horizon: "4h", precision: null, directionAccuracy: null, status: "evaluating" },
    { name: "Niveaux Clés & Supports/Résistances", horizon: "24h", precision: null, directionAccuracy: null, status: "evaluating" },
    { name: "Régime de Marché & Volatilité", horizon: "7j", precision: null, directionAccuracy: null, status: "evaluating" },
    { name: "Consensus Avenqo AI (Multi-analyses)", horizon: "Global", precision: null, directionAccuracy: null, status: "evaluating" },
  ];

  const handleRunBacktest = async () => {
    setRunningBacktest(true);
    setBacktestError("");
    try {
      const resp = await apiFetch("/api/v1/trading/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          interval,
          strategy: "crossover_sma",
          fast_period: 10,
          slow_period: 30,
          fee_rate: 0.001,
          slippage_rate: 0.0005,
        }),
      });
      if (!resp.ok) {
        setBacktestError("Calcul du backtest indisponible pour cet actif");
        return;
      }
      const data: BacktestData = await resp.json();
      setBacktestResult(data);
    } catch {
      setBacktestError("Erreur réseau lors de l'exécution du backtest");
    } finally {
      setRunningBacktest(false);
    }
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Table de performance des modèles */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
          <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
            <span>⚙️</span> {copy.modelsPerformanceTitle}
          </h3>
          <span className="rounded bg-slate-900 px-2 py-0.5 text-[10px] text-amber-400 border border-amber-800/40">
            {copy.modelStatusEvaluating}
          </span>
        </div>

        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-800 text-[11px] text-slate-400">
                <th className="pb-2 font-semibold">{copy.modelName}</th>
                <th className="pb-2 font-semibold text-right">{copy.modelMae}</th>
                <th className="pb-2 font-semibold text-right">{copy.modelMape}</th>
                <th className="pb-2 font-semibold text-right">{copy.modelDirection}</th>
                <th className="pb-2 font-semibold text-right">{copy.modelStatus}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {models.map((m) => (
                <tr key={m.name} className="hover:bg-slate-900/40">
                  <td className="py-2 font-bold text-white font-sans">{m.name}</td>
                  <td className="py-2 text-right font-mono text-cyan-400 font-semibold">{m.horizon}</td>
                  <td className="py-2 text-right text-slate-400 font-mono">
                    {m.precision !== null ? `${m.precision.toFixed(1)} %` : "—"}
                  </td>
                  <td className="py-2 text-right text-slate-400 font-mono">
                    {m.directionAccuracy !== null ? `${m.directionAccuracy.toFixed(1)} %` : "—"}
                  </td>
                  <td className="py-2 text-right">
                    <span className="rounded bg-amber-950/80 px-1.5 py-0.5 text-[9px] font-sans font-bold text-amber-400 border border-amber-800/50">
                      {copy.modelStatusEvaluating}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Carte Strategy Lab & Backtest */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
          <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
            <span>🧪</span> {copy.strategyLabTitle}
          </h3>
          <span className="text-[10px] text-slate-400 font-mono">SMA 10/30 · {symbol}</span>
        </div>

        {/* Hypothèses du modèle (frais, slippage, annualisation) */}
        <div className="flex items-center justify-between text-[11px] text-slate-400 bg-slate-900/40 border border-slate-800/60 rounded-lg px-2.5 py-1">
          <span>{copy.backtestAssumptions}</span>
          <span className="font-mono text-cyan-300">
            {backtestResult?.assumptions
              ? `Frais: ${backtestResult.assumptions.fee_rate_percent} % · Slippage: ${backtestResult.assumptions.slippage_rate_percent} %`
              : copy.backtestFeesSlippage}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-2.5">
            <span className="text-slate-400">{copy.strategyReturn}</span>
            <div className="text-lg font-bold font-mono text-emerald-400">
              {backtestResult?.strategy_return !== null && backtestResult?.strategy_return !== undefined
                ? `${backtestResult.strategy_return >= 0 ? "+" : ""}${(backtestResult.strategy_return * 100).toFixed(1)} %`
                : copy.backtestNotRun}
            </div>
            <span className="text-[10px] text-slate-500">
              {backtestResult ? `${backtestResult.candles_count} bougies réelles` : "En attente d'exécution"}
            </span>
          </div>

          <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-2.5">
            <span className="text-slate-400">{copy.strategyHolding}</span>
            <div className="text-lg font-bold font-mono text-slate-300">
              {backtestResult?.holding_return !== null && backtestResult?.holding_return !== undefined
                ? `${backtestResult.holding_return >= 0 ? "+" : ""}${(backtestResult.holding_return * 100).toFixed(1)} %`
                : copy.backtestNotRun}
            </div>
            <span className="text-[10px] text-slate-500">
              {backtestResult ? "Même fenêtre temporelle" : "Non calculé"}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between text-xs rounded-xl border border-slate-800/80 bg-slate-900/40 p-2.5">
          <div>
            <span className="text-slate-400">{copy.strategySharpe}:</span>{" "}
            <span className="font-mono font-bold text-cyan-400">
              {backtestResult?.sharpe_ratio !== null && backtestResult?.sharpe_ratio !== undefined
                ? backtestResult.sharpe_ratio.toFixed(2)
                : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-400">Max DD:</span>{" "}
            <span className="font-mono font-bold text-rose-400">
              {backtestResult?.max_drawdown !== null && backtestResult?.max_drawdown !== undefined
                ? `${(backtestResult.max_drawdown * 100).toFixed(1)} %`
                : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-400">Win Rate:</span>{" "}
            <span className="font-mono font-bold text-emerald-400">
              {backtestResult?.win_rate !== null && backtestResult?.win_rate !== undefined
                ? `${backtestResult.win_rate.toFixed(1)} %`
                : "—"}
            </span>
          </div>
          <div>
            <span className="text-slate-400">Ordres:</span>{" "}
            <span className="font-mono font-bold text-slate-300">
              {backtestResult ? `${backtestResult.closed_trades_count ?? backtestResult.trades_count}` : "—"}
            </span>
          </div>
        </div>

        {/* Position en cours (distinction claire des ordres clos) */}
        {backtestResult?.open_position && (
          <div className="text-[10px] text-cyan-300 bg-cyan-950/40 border border-cyan-800/40 rounded-lg px-2.5 py-1 flex items-center justify-between">
            <span className="font-semibold">{copy.backtestOpenPosition} :</span>
            <span className="font-mono">
              P&L latent : {backtestResult.open_position.unrealized_return >= 0 ? "+" : ""}{(backtestResult.open_position.unrealized_return * 100).toFixed(1)} % ({backtestResult.open_position.bars_held} bougies)
            </span>
          </div>
        )}

        <button
          type="button"
          onClick={handleRunBacktest}
          disabled={runningBacktest}
          className="w-full rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 py-2.5 text-xs font-bold text-white shadow-md hover:from-purple-500 hover:to-indigo-500 transition disabled:opacity-50"
        >
          {runningBacktest ? copy.backtestExecuting : copy.strategyLabBacktest}
        </button>

        {backtestResult && (
          <div className="space-y-1 text-center pt-1">
            <p className="text-[10px] text-emerald-400 font-semibold">
              ✓ Backtest déterministe validé sur {backtestResult.candles_count} bougies historiques ({symbol} · {interval}).
            </p>
            <p className="text-[9px] text-slate-500 leading-tight">
              🛡️ {backtestResult.disclaimer}
            </p>
          </div>
        )}

        {backtestError && (
          <p className="text-center text-[10px] text-rose-400 font-semibold">
            {backtestError}
          </p>
        )}

        {!backtestResult && !backtestError && (
          <p className="text-center text-[10px] text-slate-500">
            Aucun résultat fictif. Cliquez pour calculer sur données réelles de marché.
          </p>
        )}
      </div>
    </div>
  );
}
