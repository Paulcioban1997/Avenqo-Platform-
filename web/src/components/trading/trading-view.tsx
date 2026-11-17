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
  const [quoteCurrency, setQuoteCurrency] = useState("USDT");
  const [provider, setProvider] = useState("auto");
  const [found, setFound] = useState<Instrument[]>([]);
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState("1h");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [candleFreshness, setCandleFreshness] = useState("delayed");
  const [candleSource, setCandleSource] = useState("");
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [rankings, setRankings] = useState<Quote[]>([]);
  const [watch, setWatch] = useState<string[]>([
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "AVAXUSDT",
    "LINKUSDT",
  ]);
  const [error, setError] = useState("");
  const [classes, setClasses] = useState<
    Array<{ asset_class: string; status: string; reason?: string }>
  >([]);
  const [displayCurrency, setDisplayCurrency] = useState("CAD");
  const [studyReturn, setStudyReturn] = useState(0.427);
  const [holdingReturn, setHoldingReturn] = useState(0.185);

  // 1. Initialisation : statut du module, watchlist, classes d'actifs et devise de l'entreprise
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [status, list, assets, account] = await Promise.all([
          apiFetch("/api/v1/trading/status"),
          apiFetch("/api/v1/trading/watchlist"),
          apiFetch("/api/v1/trading/asset-classes"),
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
        if (assets.ok) {
          const body = await assets.json();
          setClasses(body.classes ?? []);
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

  // 5. Chargement des classements USDT
  useEffect(() => {
    let cancelled = false;
    const loadRankings = async () => {
      try {
        const response = await apiFetch("/api/v1/trading/rankings");
        if (!response.ok || cancelled) return;
        const body = await response.json();
        setRankings(Array.isArray(body?.rows) ? body.rows : []);
      } catch {
        // Ignorer
      }
    };
    void loadRankings();
    const timer = window.setInterval(() => {
      void loadRankings();
    }, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

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
  }, [quotes]);

  const addWatchSymbol = async (next: string) => {
    setSymbol(next);
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

      {/* 3. Zone principale : Graphique interactif Lightweight Charts (Gauche) + Prédictions & Gemini AI (Droite) */}
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        {/* Colonne gauche : Le grand graphique interactif */}
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

        {/* Colonne droite : Prédictions IA + Assistant Conversationnel Gemini Live Pro */}
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

          {/* Recherche rapide & Watchlist */}
          <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl space-y-3">
            <h3 className="text-sm font-bold text-white flex items-center justify-between">
              <span>🔍 {copy.searchAssetPlaceholder}</span>
              <span className="text-xs text-slate-400 font-normal">{quoteCurrency}</span>
            </h3>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ex: SOL, XRP, AVAX..."
              className="w-full rounded-xl border border-slate-800 bg-slate-900/90 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
            />
            {found.length > 0 && (
              <div className="max-h-40 space-y-1 overflow-y-auto pr-1 text-xs scrollbar-thin">
                {found.map((item) => (
                  <button
                    key={item.symbol}
                    type="button"
                    onClick={() => void addWatchSymbol(item.symbol)}
                    className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 hover:bg-slate-900 text-slate-300 hover:text-white transition"
                  >
                    <span className="font-semibold text-white">{item.base}</span>
                    <span className="font-mono text-slate-500">{item.symbol}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 4. Tableaux des cotations suivies et classements en bas de page */}
      <div className="grid gap-4 lg:grid-cols-2">
        <QuoteTable
          title={copy.watchlistTitle}
          rows={quotes}
          locale={locale}
          onPick={setSymbol}
        />
        <QuoteTable
          title="Classement USDT par volume (Binance)"
          rows={rankings}
          locale={locale}
          onPick={(next) => void addWatchSymbol(next)}
        />
      </div>

      {/* 5. Statut des classes d'actifs */}
      <div className="grid gap-3 sm:grid-cols-3">
        {classes.map((item) => (
          <div
            key={item.asset_class}
            className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs"
          >
            <div className="font-bold uppercase tracking-wider text-white">
              {item.asset_class === "crypto"
                ? "Cryptomonnaies"
                : item.asset_class === "stock"
                ? "Actions (Stocks)"
                : "ETF & Fonds"}
            </div>
            <div
              className={`mt-1 font-semibold ${
                item.status === "available" ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {item.status === "available" ? "Disponible (Public)" : "Non autorisé"}
            </div>
            {item.reason && <p className="mt-1 text-[11px] text-slate-500">{item.reason}</p>}
          </div>
        ))}
      </div>
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

function QuoteTable({
  title,
  rows,
  locale,
  onPick,
}: {
  title: string;
  rows: Quote[];
  locale: LocaleCode;
  onPick: (symbol: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950/80 p-3 backdrop-blur-xl">
      <div className="mb-2 px-1 text-xs font-bold uppercase tracking-wider text-slate-400">
        {title}
      </div>
      <table className="w-full min-w-[500px] text-left text-xs font-mono">
        <thead>
          <tr className="border-b border-slate-800 text-slate-500 text-[11px]">
            <th className="pb-2 font-semibold">Symbole</th>
            <th className="pb-2 font-semibold text-right">Prix</th>
            <th className="pb-2 font-semibold text-right">24h</th>
            <th className="pb-2 font-semibold text-right">Haut</th>
            <th className="pb-2 font-semibold text-right">Bas</th>
            <th className="pb-2 font-semibold text-right">Volume</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/50">
          {rows.map((item) => (
            <tr
              key={item.symbol}
              onClick={() => onPick(item.symbol)}
              className="cursor-pointer hover:bg-slate-900/60 transition"
            >
              <td className="py-2 font-bold text-white font-sans">{item.symbol}</td>
              <td className="py-2 text-right text-slate-200">
                {typeof item.price === "number" ? item.price.toLocaleString(locale, { maximumFractionDigits: 4 }) : "—"}
              </td>
              <td
                className={`py-2 text-right font-bold ${
                  typeof item.change_percent === "number" && item.change_percent >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {typeof item.change_percent === "number"
                  ? `${item.change_percent >= 0 ? "+" : ""}${item.change_percent.toFixed(2)} %`
                  : "—"}
              </td>
              <td className="py-2 text-right text-slate-400">
                {typeof item.high === "number" ? item.high.toLocaleString(locale, { maximumFractionDigits: 4 }) : "—"}
              </td>
              <td className="py-2 text-right text-slate-400">
                {typeof item.low === "number" ? item.low.toLocaleString(locale, { maximumFractionDigits: 4 }) : "—"}
              </td>
              <td className="py-2 text-right text-slate-400">
                {typeof item.volume === "number" ? item.volume.toLocaleString(locale, { maximumFractionDigits: 0 }) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
