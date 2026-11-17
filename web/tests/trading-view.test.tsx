import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TRADING_COPY } from "../src/lib/i18n/trading-copy";
import { CANONICAL_LOCALES } from "../src/lib/i18n/canonical-locales.generated";
import { TradingTickerBand, type TickerItem } from "../src/components/trading/trading-ticker-band";
import { PredictionPanel } from "../src/components/trading/prediction-panel";

// Mock des composants dépendants de canvas/lightweight-charts pour tests jsdom
vi.mock("lightweight-charts", () => ({
  createChart: () => ({
    applyOptions: vi.fn(),
    addSeries: () => ({
      setData: vi.fn(),
      coordinateToPrice: vi.fn(),
      priceScale: () => ({ applyOptions: vi.fn() }),
    }),
    priceScale: () => ({ applyOptions: vi.fn() }),
    timeScale: () => ({ fitContent: vi.fn() }),
    subscribeCrosshairMove: vi.fn(),
    remove: vi.fn(),
  }),
  CandlestickSeries: {},
  HistogramSeries: {},
  LineSeries: {},
  ColorType: { Solid: 0 },
  CrosshairMode: { Normal: 0 },
}));

describe("Avenqo Trading AI 2.0 — I18n & Completeness", () => {
  it("covers all 44 canonical locales in TRADING_COPY without missing keys", () => {
    const requiredKeys: (keyof typeof TRADING_COPY.fr)[] = [
      "title",
      "subtitle",
      "marketsOpen",
      "marketsClosed",
      "realtimeFeed",
      "delayedFeed",
      "chartInteractive",
      "priceAxisLeft",
      "priceAxisRight",
      "hoverDate",
      "hoverOpen",
      "hoverHigh",
      "hoverLow",
      "hoverClose",
      "hoverVolume",
      "hoverCursorPrice",
      "predictionTitle",
      "predictionStatus",
      "aiChatTitle",
      "aiVoiceTrading",
      "portfolioTitle",
      "modelsPerformanceTitle",
      "strategyLabTitle",
    ];

    expect(CANONICAL_LOCALES.length).toBe(44);

    for (const locale of CANONICAL_LOCALES) {
      const copy = TRADING_COPY[locale.code];
      expect(copy, `Locale ${locale.code} missing from TRADING_COPY`).toBeDefined();
      for (const key of requiredKeys) {
        expect(copy[key], `Missing key '${key}' in locale '${locale.code}'`).toBeTruthy();
      }
    }
  });

  it("renders the TradingTickerBand with real market status and truthful stock unavailability", () => {
    const tickers: TickerItem[] = [
      {
        symbol: "BTCUSDT",
        label: "BTC/USDT",
        price: 86421.5,
        changePercent: 2.34,
        currency: "USDT",
        assetClass: "crypto",
        status: "delayed",
      },
      {
        symbol: "AAPL",
        label: "AAPL",
        price: null,
        changePercent: null,
        currency: "USD",
        assetClass: "stock",
        status: "unavailable",
      },
    ];

    render(
      <TradingTickerBand
        tickers={tickers}
        activeSymbol="BTCUSDT"
        onSelectSymbol={vi.fn()}
        locale="fr"
        displayCurrency="CAD"
      />
    );

    expect(screen.getByText("Marchés ouverts")).toBeInTheDocument();
    expect(screen.getByText("BTC/USDT")).toBeInTheDocument();
    expect(screen.getByText("+2.34 %")).toBeInTheDocument();
    // Transparence : AAPL indique explicitement Indisponible
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Indisponible")).toBeInTheDocument();
    expect(screen.getByText("CAD")).toBeInTheDocument();
  });

  it("renders the PredictionPanel with truthful statistical evaluation status and no fake prices", () => {
    render(
      <PredictionPanel
        symbol="BTCUSDT"
        currentPrice={86421.5}
        indicators={{
          sma_20: 85000,
          ema_12: 85800,
          rsi_14: 64.2,
          macd: { line: 15.2, signal: 10.1, histogram: 5.1 },
          bollinger: { middle: 85000, upper: 88000, lower: 82000 },
        }}
        locale="fr"
        currency="USDT"
      />
    );

    expect(screen.getByText(/Prédictions IA Quantitatives/i)).toBeInTheDocument();
    expect(screen.getByText("En cours d'évaluation hors-échantillon")).toBeInTheDocument();
    expect(screen.getByText("Achat (Tendance haussière)")).toBeInTheDocument();
    expect(screen.getByText(/Validation Active/i)).toBeInTheDocument();
  });
});
