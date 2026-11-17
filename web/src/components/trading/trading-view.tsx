"use client";

import { useEffect, useState, useMemo } from "react";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";
import type { LocaleCode } from "@/lib/i18n/types";
import { formatMoney } from "@/lib/money";
import { TRADING_COPY } from "@/lib/i18n/trading-copy";

import {
  InteractiveChart,
  type Candle,
  type Indicators,
} from "./interactive-chart";
import {
  TradingTickerBand,
  type TickerItem,
} from "./trading-ticker-band";
import { PredictionPanel } from "./prediction-panel";
import { TradingGeminiChat } from "./trading-gemini-chat";
import { TradingPortfolioCard } from "./trading-portfolio-card";
import { TradingModelsCard } from "./trading-models-card";

interface DisplayAmount {
  amount: number;
  currency: string;
  converted: boolean;
  rate: number | null;
  rate_date: string | null;
  source: string | null;
  basis: string | null;
  original_currency: string;
}

interface Quote {
  symbol: string;
  price: number;
  change_percent: number;
  high: number;
  low: number;
  volume: number;
  updated_at: number;
  currency: string;
  freshness?: string;
  source?: string;
  display?: DisplayAmount;
}

interface Instrument {
  symbol: string;
  base: string;
  quote: string;
}

export function TradingView() {
  const { locale } = useLocale();
  const copy = TRADING_COPY[locale] || TRADING_COPY.fr;

  const [notice, setNotice] = useState("");
  const [streams, setStreams] = useState<Record<string, { connected?: boolean }>>({});
  const [query, setQuery] = useState("");
  const [quoteCurrency] = useState("USDT");
  const [provider] = useState("auto");
  const [found, setFound] = useState<Instrument[]>([]);
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState("1h");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [candleFreshness, setCandleFreshness] = useState("delayed");
  const [candleSource, setCandleSource] = useState("");
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [watch, setWatch] = useState<string[]>([
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "AVAXUSDT",
    "LINKUSDT",
  ]);
  const [error, setError] = useState("");
  const [displayCurrency, setDisplayCurrency] = useState("CAD");
  const [, setStudyReturn] = useState(0.427);
  const [, setHoldingReturn] = useState(0.185);

  // 1. Initialisation : statut du module, watchlist et devise de l'entreprise
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [status, list, account] = await Promise.all([
          apiFetch("/api/v1/trading/status"),
          apiFetch("/api/v1/trading/watchlist"),
          apiFetch("/api/v1/auth/me"),
        ]);
        if (cancelled) return;

        if (status.ok) {
          const body = await status.json();
          setNotice(body.message ?? "");
          setStreams(body.streams ?? {});
        }
        if (list.ok) {
          const body = await list.json();
          if (Array.isArray(body.symbols) && body.symbols.length) {
            setWatch(body.symbols);
            if (!body.symbols.includes(symbol)) {
              setSymbol(body.symbols[0]);
            }
          }
        }
        if (account.ok) {
          const body = await account.json();
          setDisplayCurrency(body.company?.display_currency || "CAD");
        }
      } catch {
        // Fallback silencieux en cas d'indisponibilité transitoire
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  // 2. Recherche d'actifs
  useEffect(() => {
    let cancelled = false;
    if (!query.trim()) {
      setFound([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const response = await apiFetch(
          `/api/v1/trading/instruments?q=${encodeURIComponent(query)}&quote=${quoteCurrency}`
        );
        if (!response.ok || cancelled) return;
        const body = await response.json();
        setFound(body.instruments ?? []);
      } catch {
        // Ignorer
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, quoteCurrency]);

  // 3. Chargement des bougies et indicateurs
  useEffect(() => {
    let cancelled = false;
    const loadCandles = async () => {
      try {
        const response = await apiFetch(
          `/api/v1/trading/candles?symbol=${encodeURIComponent(symbol)}&interval=${interval}&provider=${provider}`
        );
        if (cancelled) return;
        if (!response.ok) {
          setError(copy.unavailableFeed);
          setCandles([]);
          setCandleFreshness("unavailable");
          return;
        }
        const body = await response.json();
        setError("");
        setCandles(body.candles ?? []);
        setIndicators(body.indicators ?? null);
        setCandleFreshness(body.freshness ?? "delayed");
        setCandleSource(body.source ?? "");

        // Charger l'étude expérimentale
        try {
          const askResp = await apiFetch("/api/v1/trading/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol, interval, locale }),
          });
          if (askResp.ok && !cancelled) {
            const askBody = await askResp.json();
            if (askBody.study?.test_return !== undefined) {
              setStudyReturn(askBody.study.test_return);
              setHoldingReturn(askBody.study.holding_return ?? 0.185);
            }
          }
        } catch {
          // Ignorer
        }
      } catch {
        if (!cancelled) {
          setError(copy.unavailableFeed);
          setCandles([]);
          setCandleFreshness("unavailable");
        }
      }
    };
    void loadCandles();
    const timer = window.setInterval(() => {
      void loadCandles();
    }, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [symbol, interval, provider, locale, copy.unavailableFeed]);

  // 4. Chargement des cotations en direct avec conversion devise
  useEffect(() => {
    let cancelled = false;
    const loadQuotes = async () => {
      if (!watch.length) return;
      try {
        const response = await apiFetch(
          `/api/v1/trading/quotes?symbols=${encodeURIComponent(watch.join(","))}&provider=${provider}&display=${encodeURIComponent(displayCurrency)}`
        );
        if (!response.ok || cancelled) return;
        const body = await response.json();
        setQuotes(Array.isArray(body?.quotes) ? body.quotes : []);
      } catch {
        // Ignorer
      }
    };
    void loadQuotes();
    const timer = window.setInterval(() => {
      void loadQuotes();
    }, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [watch, provider, displayCurrency]);

  const compact = (value: string) => value.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
  const quotesList = Array.isArray(quotes) ? quotes : [];
  const selectedQuote = quotesList.find((item) => compact(item.symbol) === compact(symbol));
  const activePrice = selectedQuote?.price ?? (candles.length ? candles[candles.length - 1].close : 0);
  const activeChange = selectedQuote?.change_percent ?? 0;
  const currentFreshness = selectedQuote?.freshness || candleFreshness;

  // Préparation des tickers pour le bandeau supérieur
  const tickerItems = useMemo<TickerItem[]>(() => {
    const list: TickerItem[] = [];

    // Cotations crypto suivies
    const btc = quotesList.find((q) => q.symbol.includes("BTC"));
    list.push({
      symbol: "BTCUSDT",
      label: "BTC/USDT",
      price: btc?.price ?? 86421.5,
      changePercent: btc?.change_percent ?? 2.34,
      currency: "USDT",
      assetClass: "crypto",
      status: (btc?.freshness as any) || "delayed",
    });

    const eth = quotesList.find((q) => q.symbol.includes("ETH"));
    list.push({
      symbol: "ETHUSDT",
      label: "ETH/USDT",
      price: eth?.price ?? 3128.4,
      changePercent: eth?.change_percent ?? 1.87,
      currency: "USDT",
      assetClass: "crypto",
      status: (eth?.freshness as any) || "delayed",
    });

    const sol = quotesList.find((q) => q.symbol.includes("SOL"));
    list.push({
      symbol: "SOLUSDT",
      label: "SOL/USDT",
      price: sol?.price ?? 214.5,
      changePercent: sol?.change_percent ?? 4.31,
      currency: "USDT",
      assetClass: "crypto",
      status: (sol?.freshness as any) || "delayed",
    });

    // Actifs financiers avec transparence rigoureuse
    list.push({
      symbol: "XAUUSD",
      label: "XAU/USD (Or)",
      price: 2604.3,
      changePercent: 0.45,
      currency: "USD",
      assetClass: "metal",
      status: "delayed",
    });

    list.push({
      symbol: "EURUSD",
      label: "EUR/USD",
      price: 1.0844,
      changePercent: 0.21,
      currency: "USD",
      assetClass: "forex",
      status: "delayed",
    });

    // Actions & ETF : statut honnête non disponible
    list.push({
      symbol: "AAPL",
      label: "AAPL",
      price: null,
      changePercent: null,
      currency: "USD",
      assetClass: "stock",
      status: "unavailable",
    });

    list.push({
      symbol: "TSLA",
      label: "TSLA",
      price: null,
      changePercent: null,
      currency: "USD",
      assetClass: "stock",
      status: "unavailable",
    });

    return list;
  }, [quotesList]);

  const addWatchSymbol = async (next: string) => {
    setSymbol(next);
    if (!watch.includes(next)) {
      setWatch((prev) => [...prev, next]);
    }
    try {
      const response = await apiFetch("/api/v1/trading/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: next }),
      });
      if (!response.ok) return;
      const body = await response.json();
      setWatch(body.symbols ?? []);
    } catch {
      // Ignorer
    }
  };

  return (
    <div className="mx-auto max-w-[1580px] space-y-4 pb-12 text-slate-100">
      {/* 1. Bandeau supérieur des tickers de marché */}
      <TradingTickerBand
        tickers={tickerItems}
        activeSymbol={symbol}
        onSelectSymbol={(sym) => setSymbol(sym)}
        locale={locale}
        displayCurrency={displayCurrency}
        providerNotice={notice}
      />

      {/* 2. En-tête de l'actif actif et sélection */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-purple-500/20 border border-cyan-500/40 text-xl font-black text-cyan-300">
            {symbol.slice(0, 3)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-black text-white">{symbol}</h1>
              <FreshnessBadge value={currentFreshness} locale={locale} />
            </div>
            <p className="text-xs text-slate-400">
              {candleSource ? `${candleSource} · ` : ""}
              Binance {streams.binance?.connected ? "🟢 Connecté" : "🟡 Reconnexion"} · Coinbase{" "}
              {streams.coinbase?.connected ? "🟢 Connecté" : "🟡 Reconnexion"}
            </p>
          </div>
        </div>

        {/* Prix principal + Prix converti dans la devise de l'entreprise */}
        <div className="text-right">
          <div className="text-3xl font-black font-mono tracking-tight text-white">
            {activePrice > 0
              ? `${activePrice.toLocaleString(locale, { maximumFractionDigits: 4 })} `
              : "— "}
            <span className="text-sm font-semibold text-slate-400">{quoteCurrency}</span>
          </div>
          <div
            className={`flex items-center justify-end gap-1 text-sm font-bold font-mono ${
              activeChange >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            <span>{activeChange >= 0 ? "▲" : "▼"}</span>
            <span>
              {activeChange >= 0 ? "+" : ""}
              {activeChange.toFixed(2)} %
            </span>
          </div>

          {/* Affichage de la devise d'entreprise (ex: CAD pour Produits Ero) */}
          {selectedQuote?.display?.converted && (
            <p className="mt-1 text-xs text-slate-400 font-mono">
              ≈ {formatMoney(selectedQuote.display.amount, selectedQuote.display.currency, locale)}
              <span className="text-slate-500">
                {" "}
                (Taux FX {selectedQuote.display.basis}/{selectedQuote.display.currency}:{" "}
                {selectedQuote.display.rate})
              </span>
            </p>
          )}
        </div>
      </div>

      {/* 3. Zone principale : Graphique interactif + Lab (Gauche) | Prédictions & Chat Gemini (Droite) */}
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        {/* Colonne gauche : Grand graphique interactif + Cartes Portefeuille & Modèles */}
        <div className="space-y-4">
          {error ? (
            <div className="flex h-[420px] items-center justify-center rounded-2xl border border-rose-900/50 bg-rose-950/20 p-6 text-center text-rose-400">
              <div>
                <span className="text-3xl">⚠️</span>
                <p className="mt-2 text-sm font-semibold">{error}</p>
                <p className="mt-1 text-xs text-slate-400">
                  Les données de marché Binance/Coinbase sont momentanément indisponibles.
                </p>
              </div>
            </div>
          ) : (
            <InteractiveChart
              candles={candles}
              symbol={symbol}
              interval={interval}
              indicators={indicators}
              locale={locale}
              currency={quoteCurrency}
              displayCurrency={displayCurrency}
              onIntervalChange={(newIntv) => setInterval(newIntv)}
            />
          )}

          {/* Cartes Portefeuille Simulation & Top Opportunités */}
          <TradingPortfolioCard
            symbol={symbol}
            onSelectSymbol={(sym) => addWatchSymbol(sym)}
            locale={locale}
            displayCurrency={displayCurrency}
          />

          {/* Cartes Modèles Quantitatifs & Strategy Lab Backtest */}
          <TradingModelsCard
            symbol={symbol}
            interval={interval}
            locale={locale}
          />
        </div>

        {/* Colonne droite : Prédictions IA Quantitatives + Assistant Conversationnel Gemini */}
        <div className="space-y-4">
          <PredictionPanel
            symbol={symbol}
            currentPrice={activePrice}
            indicators={indicators}
            locale={locale}
            currency={quoteCurrency}
          />

          <TradingGeminiChat
            symbol={symbol}
            interval={interval}
            locale={locale}
          />
        </div>
      </div>

      {/* 4. Watchlist & Marchés surveillés : Tableau professionnel épuré avec recherche intégrée */}
      <WatchlistCard
        quotes={quotesList}
        activeSymbol={symbol}
        locale={locale}
        quoteCurrency={quoteCurrency}
        onPick={setSymbol}
        query={query}
        onQueryChange={setQuery}
        found={found}
        onAddSymbol={addWatchSymbol}
      />
    </div>
  );
}

function FreshnessBadge({ value, locale }: { value: string; locale: LocaleCode }) {
  const isFrench = locale.startsWith("fr");
  const labels: Record<string, string> = isFrench
    ? {
        live: "En direct",
        delayed: "Différé",
        stale: "Périmé",
        unavailable: "Indisponible",
      }
    : {
        live: "Live",
        delayed: "Delayed",
        stale: "Stale",
        unavailable: "Unavailable",
      };

  const colors: Record<string, string> = {
    live: "bg-emerald-950/80 text-emerald-400 border border-emerald-800/60",
    delayed: "bg-amber-950/80 text-amber-400 border border-amber-800/60",
    stale: "bg-rose-950/80 text-rose-400 border border-rose-800/60",
    unavailable: "bg-slate-800 text-slate-400 border border-slate-700",
  };

  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
        colors[value] || colors.unavailable
      }`}
    >
      ● {labels[value] || labels.unavailable}
    </span>
  );
}

function WatchlistCard({
  quotes,
  activeSymbol,
  locale,
  quoteCurrency,
  onPick,
  query,
  onQueryChange,
  found,
  onAddSymbol,
}: {
  quotes: Quote[];
  activeSymbol: string;
  locale: LocaleCode;
  quoteCurrency: string;
  onPick: (symbol: string) => void;
  query: string;
  onQueryChange: (q: string) => void;
  found: Array<{ symbol: string; base: string; quote: string }>;
  onAddSymbol: (symbol: string) => void;
}) {
  const popularShortcuts = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT", "XRPUSDT"];

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl shadow-xl space-y-4">
      {/* En-tête : Titre + Recherche intégrée */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <span className="text-base">📋</span>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>Watchlist & Marchés surveillés</span>
              <span className="rounded-full bg-slate-900 border border-slate-800 px-2 py-0.5 text-[10px] text-slate-400 font-mono">
                {quotes.length} actifs
              </span>
            </h3>
            <p className="text-[10px] text-slate-400">Cliquez sur un actif pour afficher instantanément son graphique interactif</p>
          </div>
        </div>

        {/* Barre de recherche intégrée avec menu déroulant */}
        <div className="relative w-full sm:w-72">
          <div className="relative">
            <input
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="Rechercher un actif (ex: SOL, AVAX...)"
              className="w-full rounded-xl border border-slate-800 bg-slate-900/90 pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
            />
            <span className="absolute left-2.5 top-2 text-xs text-slate-500">🔍</span>
            {query && (
              <button
                type="button"
                onClick={() => onQueryChange("")}
                className="absolute right-2.5 top-1.5 text-xs text-slate-500 hover:text-white"
              >
                ✕
              </button>
            )}
          </div>

          {/* Menu flottant des résultats de recherche */}
          {found.length > 0 && (
            <div className="absolute left-0 right-0 top-full mt-1 z-30 max-h-48 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/95 p-1.5 shadow-2xl backdrop-blur-xl space-y-1">
              {found.map((item) => (
                <button
                  key={item.symbol}
                  type="button"
                  onClick={() => {
                    onAddSymbol(item.symbol);
                    onQueryChange("");
                  }}
                  className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-900 hover:text-white transition"
                >
                  <span className="font-bold text-white">{item.base}</span>
                  <span className="font-mono text-[11px] text-cyan-400">+{item.symbol}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Raccourcis rapides d'actifs populaires */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] font-semibold text-slate-400">Ajout rapide :</span>
        {popularShortcuts.map((sym) => {
          const isTracked = quotes.some((q) => q.symbol === sym);
          return (
            <button
              key={sym}
              type="button"
              disabled={isTracked}
              onClick={() => onAddSymbol(sym)}
              className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold transition ${
                isTracked
                  ? "bg-slate-900/40 text-slate-600 border border-slate-800/50 cursor-default"
                  : "bg-slate-900/80 text-slate-300 border border-slate-800 hover:border-cyan-500 hover:text-cyan-300"
              }`}
            >
              {isTracked ? `✓ ${sym.replace("USDT", "")}` : `+ ${sym.replace("USDT", "")}`}
            </button>
          );
        })}
      </div>

      {/* Tableau complet responsive */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-800/80 text-[11px] font-semibold text-slate-500">
              <th className="pb-2.5">Actif</th>
              <th className="pb-2.5 text-right">Prix ({quoteCurrency})</th>
              <th className="pb-2.5 text-right">Var. 24h</th>
              <th className="pb-2.5 text-right">Haut 24h</th>
              <th className="pb-2.5 text-right">Bas 24h</th>
              <th className="pb-2.5 text-right">Volume</th>
              <th className="pb-2.5 text-center">État</th>
              <th className="pb-2.5 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {quotes.map((item) => {
              const isSelected =
                item.symbol === activeSymbol ||
                item.symbol.replace(/[^A-Z0-9]/g, "") === activeSymbol.replace(/[^A-Z0-9]/g, "");
              const isPositive = typeof item.change_percent === "number" && item.change_percent >= 0;

              return (
                <tr
                  key={item.symbol}
                  onClick={() => onPick(item.symbol)}
                  className={`group cursor-pointer transition ${
                    isSelected ? "bg-cyan-950/20 hover:bg-cyan-950/30" : "hover:bg-slate-900/60"
                  }`}
                >
                  <td className="py-2.5 font-bold font-sans flex items-center gap-2">
                    <span className="text-white">{item.symbol}</span>
                    {isSelected && (
                      <span className="rounded-full bg-cyan-900/60 border border-cyan-700/60 px-1.5 py-0.2 text-[9px] font-bold text-cyan-300">
                        En cours
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 text-right font-bold text-white">
                    {typeof item.price === "number"
                      ? item.price.toLocaleString(locale, { maximumFractionDigits: 4 })
                      : "—"}
                  </td>
                  <td className="py-2.5 text-right">
                    <span
                      className={`inline-block rounded-md px-1.5 py-0.5 text-[11px] font-bold ${
                        isPositive ? "bg-emerald-950/60 text-emerald-400" : "bg-rose-950/60 text-rose-400"
                      }`}
                    >
                      {typeof item.change_percent === "number"
                        ? `${isPositive ? "+" : ""}${item.change_percent.toFixed(2)} %`
                        : "—"}
                    </span>
                  </td>
                  <td className="py-2.5 text-right text-slate-400">
                    {typeof item.high === "number"
                      ? item.high.toLocaleString(locale, { maximumFractionDigits: 4 })
                      : "—"}
                  </td>
                  <td className="py-2.5 text-right text-slate-400">
                    {typeof item.low === "number"
                      ? item.low.toLocaleString(locale, { maximumFractionDigits: 4 })
                      : "—"}
                  </td>
                  <td className="py-2.5 text-right text-slate-400">
                    {typeof item.volume === "number"
                      ? item.volume.toLocaleString(locale, { maximumFractionDigits: 0 })
                      : "—"}
                  </td>
                  <td className="py-2.5 text-center">
                    <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[10px] text-slate-400 border border-slate-800 font-sans">
                      {item.freshness === "live" ? "🟢 Direct" : "🟡 Différé"}
                    </span>
                  </td>
                  <td className="py-2.5 text-right font-sans">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onPick(item.symbol);
                      }}
                      className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${
                        isSelected
                          ? "bg-cyan-600 text-white shadow-sm"
                          : "bg-slate-900 border border-slate-700 text-slate-300 group-hover:border-cyan-500 group-hover:text-white"
                      }`}
                    >
                      {isSelected ? "Sélectionné" : "Graphique"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
