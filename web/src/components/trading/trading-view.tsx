"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

interface Candle { time: number; open: number; high: number; low: number; close: number; volume: number; }
interface Quote { symbol: string; price: number; change_percent: number; high: number; low: number; volume: number; updated_at: number; currency: string; }
interface Instrument { symbol: string; base: string; quote: string; }

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"];

export function TradingView() {
  const { locale } = useLocale();
  const french = locale.startsWith("fr");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Instrument[]>([]);
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState("1m");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [watch, setWatch] = useState<string[]>(["BTCUSDT", "ETHUSDT", "SOLUSDT"]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const loadWatch = async () => {
      const response = await apiFetch("/api/v1/trading/watchlist");
      if (!response.ok || cancelled) return;
      const body = await response.json();
      if (Array.isArray(body.symbols) && body.symbols.length) setWatch(body.symbols);
    };
    const loadStatus = async () => {
      const response = await apiFetch("/api/v1/trading/status");
      if (!response.ok || cancelled) return;
      const body = await response.json();
      setNotice(body.message ?? "");
    };
    void loadWatch();
    void loadStatus();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const response = await apiFetch(`/api/v1/trading/instruments?q=${encodeURIComponent(query)}`);
      if (!response.ok || cancelled) return;
      const body = await response.json();
      setFound(body.instruments ?? []);
    };
    const timer = window.setTimeout(() => { void load(); }, 250);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    const loadCandles = async () => {
      const response = await apiFetch(`/api/v1/trading/candles?symbol=${symbol}&interval=${interval}`);
      if (cancelled) return;
      if (!response.ok) {
        setError(french ? "Cours Binance indisponible pour cette crypto." : "Binance price is unavailable for this crypto.");
        setCandles([]);
        return;
      }
      const body = await response.json();
      setError("");
      setCandles(body.candles ?? []);
    };
    void loadCandles();
    const timer = window.setInterval(() => { void loadCandles(); }, 15000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [symbol, interval, french]);

  useEffect(() => {
    let cancelled = false;
    const loadQuotes = async () => {
      if (!watch.length) return;
      const response = await apiFetch(`/api/v1/trading/quotes?symbols=${watch.join(",")}`);
      if (!response.ok || cancelled) return;
      const body = await response.json();
      setQuotes(body.quotes ?? []);
    };
    void loadQuotes();
    const timer = window.setInterval(() => { void loadQuotes(); }, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [watch]);

  const selectedQuote = quotes.find((item) => item.symbol === symbol);
  const updated = selectedQuote ? new Date(selectedQuote.updated_at).toLocaleTimeString(locale) : "";

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

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold">Trading AI</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">{notice}</p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold">{selectedQuote ? selectedQuote.price.toLocaleString(locale, { maximumFractionDigits: 6 }) : "—"} <span className="text-sm font-medium">USDT</span></div>
          <div className={`text-sm font-semibold ${selectedQuote && selectedQuote.change_percent >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
            {selectedQuote ? `${selectedQuote.change_percent.toFixed(2)} %` : ""} {updated && `· ${updated}`}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <aside className="space-y-3 rounded-2xl border border-slate-200 p-3 dark:border-white/10">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={french ? "Chercher une crypto, ex. SOL" : "Search a crypto, e.g. SOL"}
            className="w-full rounded-lg border border-slate-200 bg-transparent px-3 py-2 text-sm dark:border-white/10"
          />
          <div className="max-h-64 space-y-1 overflow-y-auto">
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
                <button key={item} type="button" onClick={() => setSymbol(item)} className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold ${item === symbol ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-slate-100 dark:bg-white/10"}`}>
                  {item.replace("USDT", "")}
                </button>
              ))}
            </div>
            <div className="flex gap-1">
              {INTERVALS.map((item) => (
                <button key={item} type="button" onClick={() => setInterval(item)} className={`rounded-md px-2 py-1 text-xs ${item === interval ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "text-slate-500"}`}>{item}</button>
              ))}
            </div>
          </div>
          {error ? <p className="text-sm text-rose-600">{error}</p> : <CandleChart candles={candles} label={symbol} />}
          <p className="text-xs text-slate-500">{french ? "Source Binance · marché spot public · rafraîchi toutes les 3 secondes · pas un conseil" : "Binance public spot market · refreshed every 3 seconds · not advice"}</p>
        </section>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-white/10">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">{french ? "Crypto" : "Crypto"}</th>
              <th className="px-3 py-2">{french ? "Prix" : "Price"}</th>
              <th className="px-3 py-2">24 h</th>
              <th className="px-3 py-2">{french ? "Haut" : "High"}</th>
              <th className="px-3 py-2">{french ? "Bas" : "Low"}</th>
              <th className="px-3 py-2">Volume</th>
            </tr>
          </thead>
          <tbody>
            {quotes.map((item) => (
              <tr key={item.symbol} onClick={() => setSymbol(item.symbol)} className="cursor-pointer border-t border-slate-100 dark:border-white/10">
                <td className="px-3 py-2 font-semibold">{item.symbol.replace("USDT", "")}</td>
                <td className="px-3 py-2">{item.price.toLocaleString(locale, { maximumFractionDigits: 6 })} {item.currency}</td>
                <td className={`px-3 py-2 font-semibold ${item.change_percent >= 0 ? "text-emerald-600" : "text-rose-600"}`}>{item.change_percent.toFixed(2)} %</td>
                <td className="px-3 py-2">{item.high.toLocaleString(locale, { maximumFractionDigits: 6 })}</td>
                <td className="px-3 py-2">{item.low.toLocaleString(locale, { maximumFractionDigits: 6 })}</td>
                <td className="px-3 py-2">{item.volume.toLocaleString(locale, { maximumFractionDigits: 0 })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CandleChart({ candles, label }: { candles: Candle[]; label: string }) {
  const geometry = useMemo(() => {
    if (candles.length < 2) return "";
    const width = 800;
    const height = 280;
    const min = Math.min(...candles.map((candle) => candle.low));
    const max = Math.max(...candles.map((candle) => candle.high));
    const y = (value: number) => height - ((value - min) / (max - min || 1)) * (height - 8) - 4;
    const slot = width / candles.length;
    return candles.map((candle, index) => {
      const x = index * slot + slot / 2;
      const up = candle.close >= candle.open;
      const top = y(Math.max(candle.open, candle.close));
      const bottom = y(Math.min(candle.open, candle.close));
      return `<line x1="${x}" y1="${y(candle.high)}" x2="${x}" y2="${y(candle.low)}" stroke="${up ? "#059669" : "#e11d48"}" stroke-width="1" /><rect x="${x - Math.max(slot * 0.3, 1)}" y="${top}" width="${Math.max(slot * 0.6, 2)}" height="${Math.max(bottom - top, 1)}" fill="${up ? "#059669" : "#e11d48"}" />`;
    }).join("");
  }, [candles]);
  if (!geometry) return <div className="flex h-64 items-center justify-center text-sm text-slate-500">{label}</div>;
  return <svg viewBox="0 0 800 280" className="h-72 w-full" role="img" aria-label={label} dangerouslySetInnerHTML={{ __html: geometry }} />;
}
