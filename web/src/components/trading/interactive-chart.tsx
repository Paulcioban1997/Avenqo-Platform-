"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { TRADING_COPY } from "@/lib/i18n/trading-copy";
import type { LocaleCode } from "@/lib/i18n/types";
import { formatMoney } from "@/lib/money";

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Indicators {
  sma_20: number | null;
  ema_12: number | null;
  ema_26?: number | null;
  rsi_14: number | null;
  macd: { line: number | null; signal: number | null; histogram: number | null };
  bollinger: { middle: number | null; upper: number | null; lower: number | null };
}

interface HoverSnapshot {
  timeText: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  cursorPrice?: number;
  changePercent?: number;
}

interface InteractiveChartProps {
  candles: Candle[];
  symbol: string;
  interval: string;
  indicators: Indicators | null;
  locale: LocaleCode;
  currency?: string;
  displayCurrency?: string;
  onIntervalChange?: (interval: string) => void;
}

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"];

export function InteractiveChart({
  candles,
  symbol,
  interval,
  indicators,
  locale,
  currency = "USDT",
  displayCurrency = "CAD",
  onIntervalChange,
}: InteractiveChartProps) {
  const copy = TRADING_COPY[locale] || TRADING_COPY.fr;
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ema50SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const [priceScalePosition, setPriceScalePosition] = useState<"left" | "right">("left");
  const [showEma50, setShowEma50] = useState(true);
  const [showEma200, setShowEma200] = useState(true);
  const [showVolume, setShowVolume] = useState(true);
  const [showOscillators, setShowOscillators] = useState(true);
  const [hoverData, setHoverData] = useState<HoverSnapshot | null>(null);

  // Trier et dédoublonner les bougies
  const formattedData = useMemo(() => {
    if (!candles || !candles.length) return { candlePoints: [], volumePoints: [] };
    const seen = new Set<number>();
    const sorted = [...candles].sort((a, b) => a.time - b.time);
    const candlePoints = [];
    const volumePoints = [];

    for (const c of sorted) {
      const sec = Math.floor(c.time > 1e11 ? c.time / 1000 : c.time) as UTCTimestamp;
      if (seen.has(sec)) continue;
      seen.add(sec);
      const isUp = c.close >= c.open;
      candlePoints.push({
        time: sec,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      });
      volumePoints.push({
        time: sec,
        value: c.volume,
        color: isUp ? "rgba(16, 185, 129, 0.45)" : "rgba(239, 68, 68, 0.45)",
      });
    }

    return { candlePoints, volumePoints };
  }, [candles]);

  // Calcul dynamique des EMA
  const ema50Points = useMemo(() => {
    if (!formattedData.candlePoints.length) return [];
    const period = 50;
    const k = 2 / (period + 1);
    const points = [];
    let prevEma: number | null = null;

    for (let i = 0; i < formattedData.candlePoints.length; i++) {
      const c = formattedData.candlePoints[i];
      if (i < period - 1) continue;
      if (prevEma === null) {
        let sum = 0;
        for (let j = i - period + 1; j <= i; j++) {
          sum += formattedData.candlePoints[j].close;
        }
        prevEma = sum / period;
      } else {
        prevEma = c.close * k + prevEma * (1 - k);
      }
      points.push({ time: c.time, value: prevEma });
    }
    return points;
  }, [formattedData.candlePoints]);

  const ema200Points = useMemo(() => {
    if (!formattedData.candlePoints.length) return [];
    const period = 200;
    const k = 2 / (period + 1);
    const points = [];
    let prevEma: number | null = null;

    for (let i = 0; i < formattedData.candlePoints.length; i++) {
      const c = formattedData.candlePoints[i];
      if (i < period - 1) continue;
      if (prevEma === null) {
        let sum = 0;
        for (let j = i - period + 1; j <= i; j++) {
          sum += formattedData.candlePoints[j].close;
        }
        prevEma = sum / period;
      } else {
        prevEma = c.close * k + prevEma * (1 - k);
      }
      points.push({ time: c.time, value: prevEma });
    }
    return points;
  }, [formattedData.candlePoints]);

  // Initialisation et gestion du cycle de vie du graphique Lightweight Charts
  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    const width = container.clientWidth || 800;
    const height = 420;

    const chart = createChart(container, {
      width,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(51, 65, 85, 0.35)" },
        horzLines: { color: "rgba(51, 65, 85, 0.35)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(148, 163, 184, 0.6)",
          width: 1,
          style: 3,
          labelBackgroundColor: "#1e293b",
        },
        horzLine: {
          color: "rgba(148, 163, 184, 0.6)",
          width: 1,
          style: 3,
          labelBackgroundColor: "#1e293b",
        },
      },
      // Configuration de l'axe des prix À GAUCHE (demande explicite utilisateur)
      leftPriceScale: {
        visible: priceScalePosition === "left",
        borderColor: "rgba(51, 65, 85, 0.6)",
        scaleMargins: { top: 0.08, bottom: 0.18 },
      },
      rightPriceScale: {
        visible: priceScalePosition === "right",
        borderColor: "rgba(51, 65, 85, 0.6)",
        scaleMargins: { top: 0.08, bottom: 0.18 },
      },
      timeScale: {
        borderColor: "rgba(51, 65, 85, 0.6)",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // 1. Candlestick Series reliée à l'axe des prix gauche/droite
    const candleSeries = chart.addSeries(CandlestickSeries, {
      priceScaleId: priceScalePosition,
      upColor: "#10b981",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    // 2. Volume Series en overlay bas
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: "volume-overlay",
      priceFormat: { type: "volume" },
    });
    chart.priceScale("volume-overlay").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    // 3. EMA 50 (Cyan) & EMA 200 (Purple)
    const ema50Series = chart.addSeries(LineSeries, {
      priceScaleId: priceScalePosition,
      color: "#06b6d4",
      lineWidth: 2,
      crosshairMarkerVisible: true,
    });

    const ema200Series = chart.addSeries(LineSeries, {
      priceScaleId: priceScalePosition,
      color: "#a855f7",
      lineWidth: 2,
      crosshairMarkerVisible: true,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    ema50SeriesRef.current = ema50Series;
    ema200SeriesRef.current = ema200Series;

    // Détection du survol de souris : date/heure, O, H, L, C, Volume et prix exact au curseur
    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.point) {
        setHoverData(null);
        return;
      }

      const cData = param.seriesData.get(candleSeries) as
        | { open: number; high: number; low: number; close: number }
        | undefined;
      const vData = param.seriesData.get(volumeSeries) as { value: number } | undefined;
      const cursorPrice = candleSeries.coordinateToPrice(param.point.y);

      let dateStr = "";
      try {
        const timestampMs = typeof param.time === "number" ? param.time * 1000 : Date.now();
        dateStr = new Date(timestampMs).toLocaleString(locale, {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
      } catch {
        dateStr = String(param.time);
      }

      const changePct =
        cData && cData.open > 0 ? ((cData.close - cData.open) / cData.open) * 100 : undefined;

      setHoverData({
        timeText: dateStr,
        open: cData?.open,
        high: cData?.high,
        low: cData?.low,
        close: cData?.close,
        volume: vData?.value,
        cursorPrice: cursorPrice !== null ? cursorPrice : undefined,
        changePercent: changePct,
      });
    });

    // Redimensionnement automatique
    const resizeObserver = new ResizeObserver((entries) => {
      if (!entries.length || !entries[0].contentRect) return;
      const { width: newWidth } = entries[0].contentRect;
      chart.applyOptions({ width: Math.max(newWidth, 320) });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [priceScalePosition, locale]);

  // Mise à jour des données de la série
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;

    candleSeriesRef.current.setData(formattedData.candlePoints);
    if (showVolume) {
      volumeSeriesRef.current.setData(formattedData.volumePoints);
    } else {
      volumeSeriesRef.current.setData([]);
    }

    if (ema50SeriesRef.current) {
      ema50SeriesRef.current.setData(showEma50 ? ema50Points : []);
    }

    if (ema200SeriesRef.current) {
      ema200SeriesRef.current.setData(showEma200 ? ema200Points : []);
    }

    if (chartRef.current && formattedData.candlePoints.length) {
      chartRef.current.timeScale().fitContent();
    }
  }, [formattedData, ema50Points, ema200Points, showVolume, showEma50, showEma200]);

  const resetView = () => {
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  };

  const lastCandle = formattedData.candlePoints[formattedData.candlePoints.length - 1];
  const activePrice = hoverData?.close ?? lastCandle?.close ?? 0;

  return (
    <div className="relative rounded-2xl border border-slate-800 bg-slate-950/80 p-4 backdrop-blur-xl">
      {/* Barre supérieure du graphique */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Sélecteur d'intervalles */}
          <div className="flex rounded-lg bg-slate-900/90 p-0.5 border border-slate-800">
            {INTERVALS.map((intv) => (
              <button
                key={intv}
                type="button"
                onClick={() => onIntervalChange?.(intv)}
                className={`rounded px-2.5 py-1 text-xs font-semibold transition-all ${
                  intv === interval
                    ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 shadow-sm"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {intv}
              </button>
            ))}
          </div>

          {/* Toggles des indicateurs */}
          <div className="hidden sm:flex items-center gap-1.5 text-xs">
            <button
              type="button"
              onClick={() => setShowEma50(!showEma50)}
              className={`rounded-md px-2 py-1 font-mono transition ${
                showEma50
                  ? "bg-cyan-950/60 text-cyan-400 border border-cyan-700/50"
                  : "bg-slate-900 text-slate-500 border border-slate-800"
              }`}
            >
              {copy.ema50}
            </button>
            <button
              type="button"
              onClick={() => setShowEma200(!showEma200)}
              className={`rounded-md px-2 py-1 font-mono transition ${
                showEma200
                  ? "bg-purple-950/60 text-purple-400 border border-purple-700/50"
                  : "bg-slate-900 text-slate-500 border border-slate-800"
              }`}
            >
              {copy.ema200}
            </button>
            <button
              type="button"
              onClick={() => setShowVolume(!showVolume)}
              className={`rounded-md px-2 py-1 font-mono transition ${
                showVolume
                  ? "bg-emerald-950/60 text-emerald-400 border border-emerald-700/50"
                  : "bg-slate-900 text-slate-500 border border-slate-800"
              }`}
            >
              {copy.volume}
            </button>
            <button
              type="button"
              onClick={() => setShowOscillators(!showOscillators)}
              className={`rounded-md px-2 py-1 font-mono transition ${
                showOscillators
                  ? "bg-amber-950/60 text-amber-400 border border-amber-700/50"
                  : "bg-slate-900 text-slate-500 border border-slate-800"
              }`}
            >
              RSI / MACD
            </button>
          </div>
        </div>

        {/* Contrôle de l'axe des prix et réinitialisation */}
        <div className="flex items-center gap-2">
          {/* Bouton pour basculer les prix à GAUCHE / DROITE */}
          <button
            type="button"
            onClick={() => setPriceScalePosition(priceScalePosition === "left" ? "right" : "left")}
            className="flex items-center gap-1 rounded-md border border-slate-800 bg-slate-900/90 px-2.5 py-1 text-xs font-medium text-slate-300 hover:text-white hover:border-slate-700"
            title="Positionner l'axe des prix"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400"></span>
            {priceScalePosition === "left" ? copy.priceAxisLeft : copy.priceAxisRight}
          </button>

          <button
            type="button"
            onClick={resetView}
            className="rounded-md border border-slate-800 bg-slate-900/90 px-2.5 py-1 text-xs text-slate-400 hover:text-white hover:border-slate-700"
          >
            {copy.resetView}
          </button>
        </div>
      </div>

      {/* Bandeau d'inspection dynamique au survol (Crosshair Info Overlay) */}
      <div className="mb-2 flex min-h-[28px] flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono text-slate-300">
        <span className="font-semibold text-white">{symbol}</span>
        {hoverData ? (
          <>
            <span className="text-slate-400">🕒 {hoverData.timeText}</span>
            <span>
              <span className="text-slate-500">{copy.hoverOpen}:</span>{" "}
              <span className="text-slate-200">
                {hoverData.open?.toLocaleString(locale, { maximumFractionDigits: 4 })}
              </span>
            </span>
            <span>
              <span className="text-slate-500">{copy.hoverHigh}:</span>{" "}
              <span className="text-emerald-400">
                {hoverData.high?.toLocaleString(locale, { maximumFractionDigits: 4 })}
              </span>
            </span>
            <span>
              <span className="text-slate-500">{copy.hoverLow}:</span>{" "}
              <span className="text-rose-400">
                {hoverData.low?.toLocaleString(locale, { maximumFractionDigits: 4 })}
              </span>
            </span>
            <span>
              <span className="text-slate-500">{copy.hoverClose}:</span>{" "}
              <span className="font-bold text-white">
                {hoverData.close?.toLocaleString(locale, { maximumFractionDigits: 4 })}
              </span>
            </span>
            {hoverData.volume !== undefined && (
              <span>
                <span className="text-slate-500">{copy.hoverVolume}:</span>{" "}
                <span className="text-slate-300">
                  {hoverData.volume?.toLocaleString(locale, { maximumFractionDigits: 0 })}
                </span>
              </span>
            )}
            {hoverData.cursorPrice !== undefined && (
              <span className="rounded bg-cyan-950/80 px-1.5 py-0.5 text-cyan-300 border border-cyan-800/60">
                {copy.hoverCursorPrice}: {hoverData.cursorPrice.toLocaleString(locale, { maximumFractionDigits: 2 })} {currency}
              </span>
            )}
            {hoverData.changePercent !== undefined && (
              <span
                className={`font-semibold ${
                  hoverData.changePercent >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {hoverData.changePercent >= 0 ? "+" : ""}
                {hoverData.changePercent.toFixed(2)} %
              </span>
            )}
          </>
        ) : (
          <span className="text-slate-500">
            {copy.chartInteractive} · Survolez avec la souris pour inspecter OHLCV & prix
          </span>
        )}
      </div>

      {/* Conteneur principal du Canvas Lightweight Charts */}
      <div
        ref={containerRef}
        className="h-[420px] w-full cursor-crosshair overflow-hidden rounded-xl bg-slate-950/60"
        role="region"
        aria-label={`${copy.chartInteractive} - ${symbol}`}
      />

      {/* Sous-panneau Oscillateurs Techniques : RSI (14) & MACD (12, 26, 9) */}
      {showOscillators && indicators && (
        <div className="mt-3 grid gap-3 border-t border-slate-800/80 pt-3 sm:grid-cols-2">
          {/* RSI (14) Card */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-slate-300">{copy.rsi14}</span>
              <span
                className={`font-mono font-bold ${
                  (indicators.rsi_14 ?? 50) > 70
                    ? "text-rose-400"
                    : (indicators.rsi_14 ?? 50) < 30
                    ? "text-emerald-400"
                    : "text-slate-200"
                }`}
              >
                {indicators.rsi_14 !== null ? indicators.rsi_14.toFixed(2) : "—"}
              </span>
            </div>
            {/* Visual Bar representation */}
            <div className="relative mt-2 h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="absolute left-[30%] right-[30%] top-0 bottom-0 bg-slate-700/50"
                title="Zone neutre 30 - 70"
              />
              <div
                className={`h-full transition-all duration-300 ${
                  (indicators.rsi_14 ?? 50) > 70
                    ? "bg-rose-500"
                    : (indicators.rsi_14 ?? 50) < 30
                    ? "bg-emerald-500"
                    : "bg-cyan-500"
                }`}
                style={{ width: `${Math.min(Math.max(indicators.rsi_14 ?? 50, 0), 100)}%` }}
              />
            </div>
            <div className="mt-1 flex justify-between text-[10px] text-slate-500">
              <span>Survente (30)</span>
              <span>Neutre (50)</span>
              <span>Surachat (70)</span>
            </div>
          </div>

          {/* MACD Card */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-slate-300">{copy.macd}</span>
              <span
                className={`font-mono font-bold ${
                  (indicators.macd.histogram ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                Histo: {indicators.macd.histogram !== null ? indicators.macd.histogram.toFixed(4) : "—"}
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs font-mono text-slate-400">
              <span>Ligne MACD: {indicators.macd.line !== null ? indicators.macd.line.toFixed(4) : "—"}</span>
              <span>Signal: {indicators.macd.signal !== null ? indicators.macd.signal.toFixed(4) : "—"}</span>
            </div>
            <div className="mt-1 text-[10px] text-slate-500">
              {(indicators.macd.histogram ?? 0) >= 0
                ? "Divergence positive (momentum haussier)"
                : "Divergence négative (momentum baissier)"}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
