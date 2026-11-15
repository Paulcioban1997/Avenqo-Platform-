"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

interface Candle { time: number; open: number; high: number; low: number; close: number; volume: number; }
interface Quote { symbol: string; price: number; change_percent: number; high: number; low: number; volume: number; updated_at: number; currency: string; freshness?: string; source?: string; }
interface Instrument { symbol: string; base: string; quote: string; }
interface Indicators { sma_20: number | null; ema_12: number | null; rsi_14: number | null; macd: { line: number | null; signal: number | null; histogram: number | null }; bollinger: { middle: number | null; upper: number | null; lower: number | null }; }

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"];

export function TradingView() {
  const { locale } = useLocale();
  const french = locale.startsWith("fr");
  const [notice, setNotice] = useState("");
  const [streams, setStreams] = useState<Record<string, { connected?: boolean }>>({});
  const [query, setQuery] = useState("");
  const [quoteCurrency, setQuoteCurrency] = useState("USDT");
  const [provider, setProvider] = useState("auto");
  const [found, setFound] = useState<Instrument[]>([]);
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState("1m");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [candleFreshness, setCandleFreshness] = useState("unavailable");
  const [candleSource, setCandleSource] = useState("");
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [rankings, setRankings] = useState<Quote[]>([]);
  const [watch, setWatch] = useState<string[]>(["BTCUSDT", "ETHUSDT", "SOLUSDT"]);
  const [error, setError] = useState("");
  const [answer, setAnswer] = useState("");
  const [classes, setClasses] = useState<Array<{ asset_class: string; status: string; reason?: string }>>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const [status, list, assets] = await Promise.all([
        apiFetch("/api/v1/trading/status"),
        apiFetch("/api/v1/trading/watchlist"),
        apiFetch("/api/v1/trading/asset-classes"),
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
          setSymbol(body.symbols[0]);
        }
      }
      if (assets.ok) {
        const body = await assets.json();
        setClasses(body.classes ?? []);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      const response = await apiFetch(`/api/v1/trading/instruments?q=${encodeURIComponent(query)}&quote=${quoteCurrency}`);
      if (!response.ok || cancelled) return;
      const body = await response.json();
      setFound(body.instruments ?? []);
    }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query, quoteCurrency]);

  useEffect(() => {
    let cancelled = false;
    const loadCandles = async () => {
      const response = await apiFetch(`/api/v1/trading/candles?symbol=${encodeURIComponent(symbol)}&interval=${interval}&provider=${provider}`);
      if (cancelled) return;
      if (!response.ok) {
        setError(french ? "Cours public indisponible pour cette crypto." : "Public price is unavailable for this crypto.");
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
    };
    void loadCandles();
    const timer = window.setInterval(() => { void loadCandles(); }, 15000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [symbol, interval, provider, french]);

  useEffect(() => {
    let cancelled = false;
    const loadQuotes = async () => {
      if (!watch.length) return;
      const response = await apiFetch(`/api/v1/trading/quotes?symbols=${encodeURIComponent(watch.join(","))}&provider=${provider}`);
      if (!response.ok || cancelled) return;
      const body = await response.json();
      setQuotes(body.quotes ?? []);
    };
    void loadQuotes();
    const timer = window.setInterval(() => { void loadQuotes(); }, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [watch, provider]);

  useEffect(() => {
    let cancelled = false;
    const loadRankings = async () => {
      const response = await apiFetch("/api/v1/trading/rankings");
      if (!response.ok || cancelled) return;
      const body = await response.json();
      setRankings(body.rows ?? []);
    };
    void loadRankings();
    const timer = window.setInterval(() => { void loadRankings(); }, 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const selected = quotes.find((item) => item.symbol === symbol);
  const freshness = selected?.freshness || candleFreshness;

  const add = async (next: string) => {
    setSymbol(next);
    const response = await apiFetch("/api/v1/trading/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: next }),
    });
    if (!response.ok) return;
    const body = await response.json();
    setWatch(body.symbols ?? []);
  };

  const ask = async (compare = "") => {
    setAnswer(french ? "Calcul en cours…" : "Calculating…");
    const response = await apiFetch("/api/v1/trading/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, compare: compare || null, interval, locale }),
    });
    if (!response.ok) {
      setAnswer(french ? "Calcul impossible : cours indisponible." : "Calculation unavailable: price feed is down.");
      return;
    }
    const body = await response.json();
    setAnswer(body.text ?? "");
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-extrabold">Trading AI</h1>
            <FreshnessBadge value={freshness} french={french} />
          </div>
          <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">{notice}</p>
          <p className="mt-1 text-xs text-slate-500">
            Binance {streams.binance?.connected ? (french ? "connecté" : "connected") : (french ? "reconnexion" : "reconnecting")}
            {" · "}
            Coinbase {streams.coinbase?.connected ? (french ? "connecté" : "connected") : (french ? "reconnexion" : "reconnecting")}
            {candleSource ? ` · ${candleSource}` : ""}
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold">{selected ? selected.price.toLocaleString(locale, { maximumFractionDigits: 6 }) : "—"} <span className="text-sm font-medium">{selected?.currency || quoteCurrency}</span></div>
          <div className={`text-sm font-semibold ${selected && selected.change_percent >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
            {selected ? `${selected.change_percent.toFixed(2)} %` : ""}
            {selected ? ` · ${new Date(selected.updated_at).toLocaleTimeString(locale)}` : ""}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        {["USDT", "USD", "USDC", "EUR"].map((item) => (
          <button key={item} type="button" onClick={() => { setQuoteCurrency(item); setQuery(""); }} className={`rounded-lg px-2.5 py-1.5 font-semibold ${item === quoteCurrency ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-slate-100 dark:bg-white/10"}`}>{item}</button>
        ))}
        {["auto", "binance", "coinbase"].map((item) => (
          <button key={item} type="button" onClick={() => setProvider(item)} className={`rounded-lg px-2.5 py-1.5 font-semibold ${item === provider ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-slate-100 dark:bg-white/10"}`}>{item}</button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <aside className="space-y-3 rounded-2xl border border-slate-200 p-3 dark:border-white/10">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={french ? "Chercher une crypto, ex. SOL" : "Search a crypto, e.g. SOL"} className="w-full rounded-lg border border-slate-200 bg-transparent px-3 py-2 text-sm dark:border-white/10" />
          <div className="max-h-72 space-y-1 overflow-y-auto">
            {found.map((item) => (
              <button key={item.symbol} type="button" onClick={() => { void add(item.symbol); }} className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-white/10">
                <span className="font-semibold">{item.base}</span>
                <span className="text-xs text-slate-500">{item.symbol}</span>
              </button>
            ))}
          </div>
        </aside>
        <section className="space-y-3 rounded-2xl border border-slate-200 p-3 dark:border-white/10">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1">
              {watch.map((item) => (
                <button key={item} type="button" onClick={() => setSymbol(item)} className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold ${item === symbol ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-slate-100 dark:bg-white/10"}`}>{item}</button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1">
              {INTERVALS.map((item) => (
                <button key={item} type="button" onClick={() => setInterval(item)} className={`rounded-md px-2 py-1 text-xs ${item === interval ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "text-slate-500"}`}>{item}</button>
              ))}
            </div>
          </div>
          {error ? <p className="text-sm text-rose-600">{error}</p> : <CandleChart candles={candles} label={symbol} />}
          {indicators && (
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <Stat label="SMA 20" value={indicators.sma_20} />
              <Stat label="EMA 12" value={indicators.ema_12} />
              <Stat label="RSI 14" value={indicators.rsi_14} />
              <Stat label="MACD" value={indicators.macd.histogram} />
              <Stat label={french ? "Bande haute" : "Upper band"} value={indicators.bollinger.upper} />
              <Stat label={french ? "Bande basse" : "Lower band"} value={indicators.bollinger.lower} />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void ask()} className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white dark:bg-white dark:text-slate-900">{french ? "Que s'est-il passé ?" : "What changed?"}</button>
            <button type="button" onClick={() => void ask("ETHUSDT")} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold dark:border-white/10">{french ? "Comparer à ETH" : "Compare with ETH"}</button>
          </div>
          {answer && <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-200">{answer}</p>}
        </section>
      </div>

      <QuoteTable title={french ? "Liste suivie" : "Watchlist"} rows={quotes} locale={locale} onPick={setSymbol} />
      <QuoteTable title={french ? "Classement USDT par volume" : "USDT ranking by volume"} rows={rankings} locale={locale} onPick={(next) => { void add(next); }} />

      <div className="grid gap-2 sm:grid-cols-3">
        {classes.map((item) => (
          <div key={item.asset_class} className="rounded-xl border border-slate-200 p-3 text-sm dark:border-white/10">
            <div className="font-bold uppercase">{item.asset_class}</div>
            <div className={item.status === "available" ? "text-emerald-600" : "text-slate-500"}>{item.status === "available" ? (french ? "Disponible" : "Available") : (french ? "Indisponible" : "Unavailable")}</div>
            {item.reason && <p className="mt-1 text-xs text-slate-500">{item.reason}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

function FreshnessBadge({ value, french }: { value: string; french: boolean }) {
  const labels: Record<string, string> = french
    ? { live: "En direct", delayed: "Différé", stale: "Périmé", unavailable: "Indisponible", demo: "Démo" }
    : { live: "Live", delayed: "Delayed", stale: "Stale", unavailable: "Unavailable", demo: "Demo" };
  const tone = value === "live" ? "bg-emerald-100 text-emerald-800" : value === "delayed" ? "bg-amber-100 text-amber-800" : "bg-slate-200 text-slate-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${tone}`}>{labels[value] || labels.unavailable}</span>;
}

function Stat({ label, value }: { label: string; value: number | null }) {
  return <div className="rounded-lg bg-slate-50 px-2 py-1.5 dark:bg-white/5"><div className="text-slate-500">{label}</div><div className="font-semibold">{value == null ? "—" : value}</div></div>;
}

function QuoteTable({ title, rows, locale, onPick }: { title: string; rows: Quote[]; locale: string; onPick: (symbol: string) => void }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-white/10">
      <div className="px-3 py-2 text-xs font-bold uppercase text-slate-500">{title}</div>
      <table className="w-full min-w-[640px] text-left text-sm">
        <tbody>
          {rows.map((item) => (
            <tr key={item.symbol} onClick={() => onPick(item.symbol)} className="cursor-pointer border-t border-slate-100 dark:border-white/10">
              <td className="px-3 py-2 font-semibold">{item.symbol}</td>
              <td className="px-3 py-2">{item.price.toLocaleString(locale, { maximumFractionDigits: 6 })} {item.currency}</td>
              <td className={`px-3 py-2 font-semibold ${item.change_percent >= 0 ? "text-emerald-600" : "text-rose-600"}`}>{item.change_percent.toFixed(2)} %</td>
              <td className="px-3 py-2">{item.high.toLocaleString(locale, { maximumFractionDigits: 6 })}</td>
              <td className="px-3 py-2">{item.low.toLocaleString(locale, { maximumFractionDigits: 6 })}</td>
              <td className="px-3 py-2">{item.volume.toLocaleString(locale, { maximumFractionDigits: 0 })}</td>
              <td className="px-3 py-2 text-xs uppercase text-slate-500">{item.freshness || ""} {item.source || ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CandleChart({ candles, label }: { candles: Candle[]; label: string }) {
  const width = 800;
  const height = 280;
  const marks = useMemo(() => {
    if (candles.length < 2) return [];
    const min = Math.min(...candles.map((candle) => candle.low));
    const max = Math.max(...candles.map((candle) => candle.high));
    const y = (value: number) => height - ((value - min) / (max - min || 1)) * (height - 8) - 4;
    const slot = width / candles.length;
    return candles.map((candle, index) => {
      const x = index * slot + slot / 2;
      const up = candle.close >= candle.open;
      const top = y(Math.max(candle.open, candle.close));
      const bottom = y(Math.min(candle.open, candle.close));
      return { x, up, top, bottom, high: y(candle.high), low: y(candle.low), slot };
    });
  }, [candles]);
  if (!marks.length) return <div className="flex h-64 items-center justify-center text-sm text-slate-500">{label}</div>;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-72 w-full" role="img" aria-label={label}>
      {marks.map((mark, index) => (
        <g key={index}>
          <line x1={mark.x} y1={mark.high} x2={mark.x} y2={mark.low} stroke={mark.up ? "#059669" : "#e11d48"} strokeWidth="1" />
          <rect x={mark.x - Math.max(mark.slot * 0.3, 1)} y={mark.top} width={Math.max(mark.slot * 0.6, 2)} height={Math.max(mark.bottom - mark.top, 1)} fill={mark.up ? "#059669" : "#e11d48"} />
        </g>
      ))}
    </svg>
  );
}
