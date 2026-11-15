"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-request";
import { useLocale } from "@/lib/i18n/locale-context";

interface Candle { time: string; close: number; }
interface Forecast {
  validated: boolean;
  status: string;
  message: string;
  currency: string;
  estimate: { last_price: number; point: number; lower: number; upper: number; currency: string } | null;
  metrics: { model_mae: number; baseline_mae: number; directional_accuracy: number } | null;
}

export function TradingView() {
  const { locale } = useLocale();
  const french = locale.startsWith("fr");
  const [symbol, setSymbol] = useState("DEMO-SPY");
  const [notice, setNotice] = useState("");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [currency, setCurrency] = useState("USD");
  const [updatedAt, setUpdatedAt] = useState("");
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [simulation, setSimulation] = useState<string>("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setError("");
      const [status, series, outlook, paper] = await Promise.all([
        apiFetch("/api/v1/trading/status"),
        apiFetch(`/api/v1/trading/candles?symbol=${symbol}`),
        apiFetch(`/api/v1/trading/forecast?symbol=${symbol}&horizon=7d`),
        apiFetch(`/api/v1/trading/simulation?symbol=${symbol}`),
      ]);
      if (cancelled) return;
      if (!status.ok || !series.ok || !outlook.ok || !paper.ok) {
        setError(french ? "Trading AI n'est pas activé pour ce compte." : "Trading AI is not active for this account.");
        return;
      }
      const statusBody = await status.json();
      const seriesBody = await series.json();
      const outlookBody = await outlook.json();
      const paperBody = await paper.json();
      setNotice(statusBody.message);
      setCandles(seriesBody.candles ?? []);
      setCurrency(seriesBody.currency ?? "");
      setUpdatedAt(seriesBody.updated_at ?? "");
      setForecast(outlookBody);
      setSimulation(paperBody.message);
    })();
    return () => { cancelled = true; };
  }, [symbol, french]);

  const width = 640;
  const height = 180;
  const values = candles.map((candle) => candle.close);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const points = values.map((value, index) => {
    const x = values.length < 2 ? 0 : (index / (values.length - 1)) * width;
    const y = height - ((value - min) / (max - min || 1)) * height;
    return `${x},${y}`;
  }).join(" ");

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <h1 className="text-2xl font-extrabold">Trading AI</h1>
        <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">{notice}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {["DEMO-SPY", "DEMO-BTC", "DEMO-EURUSD"].map((item) => (
          <button key={item} type="button" onClick={() => setSymbol(item)} className={`rounded-lg px-3 py-2 text-sm font-semibold ${symbol === item ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "bg-slate-100 dark:bg-white/10"}`}>
            {item}
          </button>
        ))}
      </div>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      <section className="rounded-2xl border border-slate-200 p-4 dark:border-white/10">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
          <span>{french ? "Mode démo · source avenqo-demo · pas une cote réelle" : "Demo mode · source avenqo-demo · not a live quote"}</span>
          <span>{currency} · {updatedAt}</span>
        </div>
        <svg viewBox={`0 0 ${width} ${height}`} className="h-48 w-full" role="img" aria-label={symbol}>
          <polyline fill="none" stroke="currentColor" strokeWidth="2" points={points} />
        </svg>
      </section>
      <section className="grid gap-4 md:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 p-4 dark:border-white/10">
          <h2 className="font-bold">{french ? "Prévision" : "Forecast"}</h2>
          <p className="mt-2 text-sm">{forecast?.message}</p>
          {forecast?.metrics && (
            <p className="mt-2 text-xs text-slate-500">
              MAE {forecast.metrics.model_mae} · baseline {forecast.metrics.baseline_mae}
            </p>
          )}
          {forecast?.estimate && (
            <p className="mt-2 text-sm font-semibold">
              {forecast.estimate.point} {forecast.estimate.currency} ({forecast.estimate.lower} – {forecast.estimate.upper})
            </p>
          )}
        </article>
        <article className="rounded-2xl border border-slate-200 p-4 dark:border-white/10">
          <h2 className="font-bold">{french ? "Simulation" : "Simulation"}</h2>
          <p className="mt-2 text-sm">{simulation}</p>
        </article>
      </section>
    </div>
  );
}
