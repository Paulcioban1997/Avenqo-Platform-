"use client";

import { useState } from "react";
import { TRADING_COPY } from "@/lib/i18n/trading-copy";
import type { LocaleCode } from "@/lib/i18n/types";
import { formatMoney } from "@/lib/money";

interface OpportunityItem {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  currency: string;
}

interface TradingPortfolioCardProps {
  symbol: string;
  onSelectSymbol: (symbol: string) => void;
  locale: LocaleCode;
  displayCurrency: string;
  totalCadValue?: number;
  changeCad24h?: number;
}

export function TradingPortfolioCard({
  symbol,
  onSelectSymbol,
  locale,
  displayCurrency = "CAD",
  totalCadValue = 139244.44,
  changeCad24h = 2422.38,
}: TradingPortfolioCardProps) {
  const copy = TRADING_COPY[locale] || TRADING_COPY.fr;

  const [opportunities] = useState<OpportunityItem[]>([
    { symbol: "SOLUSDT", name: "Solana", price: 214.5, changePercent: 4.31, currency: "USDT" },
    { symbol: "ETHUSDT", name: "Ethereum", price: 3128.4, changePercent: 1.87, currency: "USDT" },
    { symbol: "BTCUSDT", name: "Bitcoin", price: 86421.5, changePercent: 2.34, currency: "USDT" },
    { symbol: "AVAXUSDT", name: "Avalanche", price: 38.6, changePercent: -1.15, currency: "USDT" },
    { symbol: "LINKUSDT", name: "Chainlink", price: 18.2, changePercent: 3.42, currency: "USDT" },
  ]);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Carte Portefeuille Simulation */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
              <span>💼</span> {copy.portfolioTitle}
            </h3>
            <p className="text-[10px] text-slate-400">{copy.portfolioSimulationNotice}</p>
          </div>
          <span className="rounded bg-cyan-950/80 px-2 py-0.5 text-[10px] font-mono font-bold text-cyan-400 border border-cyan-800/60">
            {displayCurrency}
          </span>
        </div>

        <div className="space-y-1">
          <div className="text-xs text-slate-400">{copy.portfolioTotalValue}</div>
          <div className="text-2xl font-extrabold font-mono text-white">
            {formatMoney(totalCadValue, displayCurrency, locale)}
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="font-semibold text-emerald-400">
              +{formatMoney(changeCad24h, displayCurrency, locale)} (+1.77 %)
            </span>
            <span className="text-slate-500">· 24h</span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-2.5 text-[11px] text-slate-400">
          <div className="flex justify-between">
            <span>Taux FX de conversion:</span>
            <span className="font-mono text-slate-200">1 USD = 1.3920 CAD (BCE/BdC)</span>
          </div>
          <div className="flex justify-between mt-1">
            <span>Règle d&apos;intégrité:</span>
            <span className="text-emerald-400">Aucun faux ordre passé</span>
          </div>
        </div>
      </div>

      {/* Carte Top Opportunités IA */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
          <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
            <span>🚀</span> {copy.topOpportunities}
          </h3>
          <span className="text-[10px] text-slate-400">Cliquez pour afficher</span>
        </div>

        <div className="space-y-1.5 max-h-[140px] overflow-y-auto pr-1 scrollbar-thin">
          {opportunities.map((opp) => (
            <div
              key={opp.symbol}
              onClick={() => onSelectSymbol(opp.symbol)}
              className={`flex items-center justify-between rounded-xl border p-2 cursor-pointer transition ${
                opp.symbol.toUpperCase() === symbol.toUpperCase()
                  ? "border-cyan-500/80 bg-cyan-950/30 text-white"
                  : "border-slate-800/60 bg-slate-900/40 hover:bg-slate-900 text-slate-300"
              }`}
            >
              <div>
                <span className="text-xs font-bold text-white">{opp.name}</span>{" "}
                <span className="text-[10px] text-slate-500 font-mono">({opp.symbol})</span>
                <div className="text-[11px] font-mono text-slate-300">
                  {opp.price.toLocaleString(locale, { maximumFractionDigits: 2 })} {opp.currency}
                </div>
              </div>

              <div className="text-right">
                <span
                  className={`inline-block rounded px-1.5 py-0.5 text-xs font-mono font-bold ${
                    opp.changePercent >= 0
                      ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800/50"
                      : "bg-rose-950/80 text-rose-400 border border-rose-800/50"
                  }`}
                >
                  {opp.changePercent >= 0 ? "+" : ""}
                  {opp.changePercent.toFixed(2)} %
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
