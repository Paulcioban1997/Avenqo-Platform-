"use client";

import { useState, useEffect } from "react";
import { TRADING_COPY } from "@/lib/i18n/trading-copy";
import type { LocaleCode } from "@/lib/i18n/types";

export interface TickerItem {
  symbol: string;
  label: string;
  price: number | null;
  changePercent: number | null;
  currency: string;
  assetClass: "crypto" | "stock" | "metal" | "forex";
  status: "live" | "delayed" | "stale" | "unavailable";
}

interface TradingTickerBandProps {
  tickers: TickerItem[];
  activeSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  locale: LocaleCode;
  displayCurrency: string;
  providerNotice?: string;
}

export function TradingTickerBand({
  tickers,
  activeSymbol,
  onSelectSymbol,
  locale,
  displayCurrency = "CAD",
  providerNotice,
}: TradingTickerBandProps) {
  const copy = TRADING_COPY[locale] || TRADING_COPY.fr;
  const [montrealTime, setMontrealTime] = useState("");

  useEffect(() => {
    const updateTime = () => {
      try {
        const now = new Date();
        const formatted = now.toLocaleTimeString(locale, {
          timeZone: "America/Montreal",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
        setMontrealTime(formatted);
      } catch {
        setMontrealTime(new Date().toLocaleTimeString());
      }
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, [locale]);

  return (
    <div className="space-y-2 rounded-2xl border border-slate-800 bg-slate-950/80 p-3 backdrop-blur-xl">
      {/* Ligne d'en-tête de statut de marché */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/60 pb-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-full bg-emerald-950/80 px-2.5 py-0.5 font-semibold text-emerald-400 border border-emerald-800/60">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            {copy.marketsOpen}
          </span>
          <span className="text-slate-400">Montréal: <strong className="font-mono text-slate-200">{montrealTime}</strong></span>
          <span className="hidden md:inline text-slate-500">·</span>
          <span className="hidden md:inline text-slate-400">{copy.dataProvider}</span>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded bg-slate-900 px-2 py-0.5 text-[11px] font-mono text-slate-300 border border-slate-800">
            {copy.companyCurrency}: <strong className="text-cyan-400">{displayCurrency}</strong>
          </span>
        </div>
      </div>

      {/* Bandeau défilant ou cliquable des actifs clés */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
        {tickers.map((t) => {
          const isSelected = t.symbol.toUpperCase() === activeSymbol.toUpperCase();
          const isAvailable = t.status !== "unavailable" && t.price !== null;

          return (
            <button
              key={t.symbol}
              type="button"
              disabled={!isAvailable}
              onClick={() => onSelectSymbol(t.symbol)}
              className={`flex shrink-0 items-center gap-2.5 rounded-xl border px-3 py-2 text-left transition-all ${
                isSelected
                  ? "border-cyan-500/80 bg-cyan-950/30 text-white shadow-md shadow-cyan-950/30"
                  : isAvailable
                  ? "border-slate-800/80 bg-slate-900/50 hover:border-slate-700 hover:bg-slate-900 text-slate-300"
                  : "border-slate-800/40 bg-slate-950/40 opacity-50 cursor-not-allowed text-slate-500"
              }`}
            >
              <div>
                <div className="flex items-center gap-1.5 text-xs font-bold text-white">
                  <span>{t.label}</span>
                  {t.assetClass === "stock" && (
                    <span className="rounded bg-slate-800 px-1 text-[9px] text-slate-400">Action</span>
                  )}
                </div>
                <div className="text-[11px] font-mono">
                  {isAvailable ? (
                    <span className="text-slate-200">
                      {t.price?.toLocaleString(locale, { maximumFractionDigits: 2 })} {t.currency}
                    </span>
                  ) : (
                    <span className="text-slate-500 text-[10px]">Indisponible</span>
                  )}
                </div>
              </div>

              {isAvailable && t.changePercent !== null && (
                <div
                  className={`rounded px-1.5 py-0.5 text-[11px] font-mono font-semibold ${
                    t.changePercent >= 0
                      ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800/50"
                      : "bg-rose-950/80 text-rose-400 border border-rose-800/50"
                  }`}
                >
                  {t.changePercent >= 0 ? "+" : ""}
                  {t.changePercent.toFixed(2)} %
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
