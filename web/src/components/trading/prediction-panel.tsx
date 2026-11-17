"use client";

import { useState } from "react";
import { TRADING_COPY } from "@/lib/i18n/trading-copy";
import type { LocaleCode } from "@/lib/i18n/types";
import type { Indicators } from "./interactive-chart";

interface PredictionPanelProps {
  symbol: string;
  currentPrice: number;
  indicators: Indicators | null;
  locale: LocaleCode;
  currency: string;
}

const HORIZONS = ["1h", "24h", "7j", "30j"] as const;

export function PredictionPanel({
  symbol,
  currentPrice,
  indicators,
  locale,
  currency = "USDT",
}: PredictionPanelProps) {
  const copy = TRADING_COPY[locale] || TRADING_COPY.fr;
  const [selectedHorizon, setSelectedHorizon] = useState<(typeof HORIZONS)[number]>("24h");

  // Analyse technique factuelle dérivée des indicateurs réels (aucun cours futur inventé)
  const macdHist = indicators?.macd?.histogram ?? 0;
  const ema12 = indicators?.ema_12 ?? currentPrice;
  const sma20 = indicators?.sma_20 ?? currentPrice;

  // Signal dérivé rigoureusement (observation factuelle de tendance sans injonction d'achat/vente)
  const isBullish = ema12 > sma20 && macdHist > 0;
  const isBearish = ema12 < sma20 && macdHist < 0;
  const signalText = isBullish
    ? copy.trendBullishObserved
    : isBearish
    ? copy.trendBearishObserved
    : copy.trendNeutralObserved;
  const signalColor = isBullish ? "text-emerald-400" : isBearish ? "text-rose-400" : "text-amber-400";
  const signalBg = isBullish ? "bg-emerald-950/40 border-emerald-800/50" : isBearish ? "bg-rose-950/40 border-rose-800/50" : "bg-amber-950/40 border-amber-800/50";

  // Volatilité basée sur l'écartement réel des bandes de Bollinger (20, 2) - Aucun pourcentage de secours inventé
  const b = indicators?.bollinger;
  const bbSpread =
    b &&
    typeof b.upper === "number" &&
    typeof b.lower === "number" &&
    typeof b.middle === "number" &&
    b.middle > 0
      ? ((b.upper - b.lower) / b.middle) * 100
      : null;

  const riskLevel =
    bbSpread !== null
      ? bbSpread > 6
        ? copy.riskHigh
        : bbSpread < 2.5
        ? copy.riskLow
        : copy.riskMedium
      : copy.insufficientData;

  return (
    <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl">
      {/* En-tête */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div>
          <h2 className="text-sm font-bold text-white flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse"></span>
            {copy.predictionTitle} ({symbol})
          </h2>
          <p className="text-[11px] text-slate-400">Moteurs d'analyse quantitative et détection de tendance Avenqo</p>
        </div>

        {/* Sélecteur d'horizon */}
        <div className="flex rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-xs font-semibold">
          {HORIZONS.map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setSelectedHorizon(h)}
              className={`rounded px-2 py-0.5 transition ${
                selectedHorizon === h
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {h}
            </button>
          ))}
        </div>
      </div>

      {/* Cartouche Cours réel & Volatilité historique */}
      <div className="rounded-xl border border-slate-800/90 bg-slate-900/50 p-3 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-400">{copy.predictionStatus}</span>
          <span className="rounded bg-amber-950/80 px-2 py-0.5 text-[10px] font-bold text-amber-400 border border-amber-800/60">
            {copy.modelStatusEvaluating}
          </span>
        </div>

        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-xs text-slate-400">{copy.predictionObservedPrice}</div>
            <div className="text-xl font-bold font-mono text-slate-200">
              {currentPrice > 0 ? (
                <span>
                  {currentPrice.toLocaleString(locale, { maximumFractionDigits: 2 })} {currency}
                </span>
              ) : (
                "—"
              )}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-slate-400">{copy.bollingerSpread}</div>
            <div className="font-mono text-xs text-cyan-400">
              {bbSpread !== null && currentPrice > 0 ? (
                `± ${bbSpread.toFixed(1)} % (${(currentPrice * (1 - bbSpread / 100)).toFixed(0)} - ${(currentPrice * (1 + bbSpread / 100)).toFixed(0)} ${currency})`
              ) : (
                <span className="text-amber-400 font-sans text-[11px]">{copy.insufficientData}</span>
              )}
            </div>
          </div>
        </div>

        {/* Statut d'évaluation honnête des modèles */}
        <div className="space-y-1 pt-1 border-t border-slate-800/60 text-xs">
          <div className="flex justify-between items-center text-[11px] text-slate-400">
            <span>Cible prédictive ({selectedHorizon})</span>
            <span className="font-mono text-[10px] text-amber-400 font-semibold">Non certifiée</span>
          </div>
          <p className="text-[10px] text-slate-500 leading-tight">
            Modèles en cours d'évaluation hors-échantillon. Aucun cours futur inventé sans validation statistique complète.
          </p>
        </div>
      </div>

      {/* Signal IA & Paramètres quantitatifs */}
      <div className={`rounded-xl border p-3 ${signalBg} space-y-2`}>
        <div className="flex items-center justify-between text-xs">
          <span className="font-bold text-slate-300">{copy.predictionSignal}</span>
          <span className={`font-bold font-mono ${signalColor}`}>{signalText}</span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-slate-800/40">
          <div>
            <span className="text-slate-400">Condition :</span>{" "}
            <span className="font-mono font-semibold text-slate-200">
              {isBullish ? "EMA > SMA & MACD > 0" : isBearish ? "EMA < SMA & MACD < 0" : "Consolidation"}
            </span>
          </div>
          <div>
            <span className="text-slate-400">{copy.predictionRisk}:</span>{" "}
            <span className="font-mono font-semibold text-slate-200">{riskLevel}</span>
          </div>
        </div>
      </div>

      {/* Note de conformité et intégrité des données */}
      <p className="text-[10px] leading-relaxed text-slate-500">
        🛡️ {copy.predictionNotice}
      </p>
    </div>
  );
}
