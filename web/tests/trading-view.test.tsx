import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { TRADING_COPY } from "../src/lib/i18n/trading-copy";
import { CANONICAL_LOCALES } from "../src/lib/i18n/canonical-locales.generated";
import { TradingTickerBand, type TickerItem } from "../src/components/trading/trading-ticker-band";
import { PredictionPanel } from "../src/components/trading/prediction-panel";
import { TradingModelsCard } from "../src/components/trading/trading-models-card";
import { TradingGeminiChat } from "../src/components/trading/trading-gemini-chat";
import { getTradingChatStrings } from "../src/lib/i18n/trading-chat-i18n";

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
    expect(screen.getByText("Tendance haussière observée")).toBeInTheDocument();
    expect(screen.getByText(/En développement/i)).toBeInTheDocument();
  });

  it("renders PredictionPanel with 'Données insuffisantes' when Bollinger indicators are missing (no fake 3.5% fallback)", () => {
    render(
      <PredictionPanel
        symbol="ETHUSDT"
        currentPrice={3120.0}
        indicators={null}
        locale="fr"
        currency="USDT"
      />
    );

    // Vérifie qu'aucun 3.5 % n'apparaît
    expect(screen.queryByText(/3\.5\s*%/)).not.toBeInTheDocument();
    // Affiche explicitement Données insuffisantes
    const insufficientBadges = screen.getAllByText("Données insuffisantes");
    expect(insufficientBadges.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Consolidation / Tendance neutre")).toBeInTheDocument();
  });

  it("renders TradingModelsCard with honest status and executes real backtest endpoint", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementationOnce(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            status: "calculated",
            candles_count: 200,
            trades_count: 8,
            strategy_return: 0.052,
            holding_return: 0.021,
            max_drawdown: -0.045,
            win_rate: 62.5,
            sharpe_ratio: 1.15,
            disclaimer: "Calcul mathématique déterministe sur bougies historiques.",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    render(<TradingModelsCard symbol="BTCUSDT" interval="1h" locale="fr" />);

    // Vérifie que les badges "Actif" inventés sont absents et remplacés par "En développement"
    const evaluatingBadges = screen.getAllByText("En développement");
    expect(evaluatingBadges.length).toBeGreaterThanOrEqual(5);

    // Initialement le backtest n'affiche aucun chiffre inventé
    expect(screen.getAllByText(/Non calculé/i).length).toBeGreaterThanOrEqual(1);

    // Déclenche le backtest
    const button = screen.getByRole("button", { name: /Lancer un Backtest/i });
    await act(async () => {
      fireEvent.click(button);
    });

    // Attend la mise à jour après appel API réel
    const successMsg = await screen.findByText(/Calcul déterministe terminé sur 200 bougies/i);
    expect(successMsg).toBeInTheDocument();
    // Ne jamais afficher "validé" comme si la rentabilité future était garantie
    expect(screen.queryByText(/Backtest déterministe validé/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Validation statistique : Non certifiée/i)).toBeInTheDocument();
    expect(screen.getByText("+5.2 %")).toBeInTheDocument();
    expect(screen.getByText("+2.1 %")).toBeInTheDocument();
    expect(screen.getByText("1.15")).toBeInTheDocument();
    expect(screen.getByText("-4.5 %")).toBeInTheDocument();
    expect(screen.getByText("62.5 %")).toBeInTheDocument();
  });

  it("renders TradingGeminiChat with genuine multilingual specialized trading questions and UI strings", () => {
    // 1. Test French
    const { unmount: unmountFr } = render(
      <TradingGeminiChat symbol="BTCUSDT" interval="1h" locale="fr" />
    );
    expect(screen.getByText("Assistant Trading AI")).toBeInTheDocument();
    expect(screen.getByText("Questions spécialisées :")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Posez votre question technique à Gemini...")).toBeInTheDocument();
    expect(screen.getByText(/Je suis l'analyste de marché Avenqo Trading AI/i)).toBeInTheDocument();
    unmountFr();

    // 2. Test Spanish
    const { unmount: unmountEs } = render(
      <TradingGeminiChat symbol="SOLUSDT" interval="4h" locale="es" />
    );
    expect(screen.getByText("Asistente Trading AI")).toBeInTheDocument();
    expect(screen.getByText("Preguntas especializadas:")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Hazle tu pregunta técnica a Gemini...")).toBeInTheDocument();
    expect(screen.getByText(/¡Hola! Soy el analista de mercado Avenqo Trading AI/i)).toBeInTheDocument();
    unmountEs();

    // 3. Test Romanian
    const { unmount: unmountRo } = render(
      <TradingGeminiChat symbol="ETHUSDT" interval="15m" locale="ro" />
    );
    expect(screen.getByText("Asistent Trading AI")).toBeInTheDocument();
    expect(screen.getByText("Întrebări specializate:")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Adresează întrebarea ta tehnică către Gemini...")).toBeInTheDocument();
    expect(screen.getByText(/Bună ziua! Sunt analistul de piață Avenqo Trading AI/i)).toBeInTheDocument();
    unmountRo();

    // 4. Test German
    const { unmount: unmountDe } = render(
      <TradingGeminiChat symbol="BTCUSDT" interval="1d" locale="de" />
    );
    expect(screen.getByText("Trading AI Assistent")).toBeInTheDocument();
    expect(screen.getByText("Spezialisierte Fragen:")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Stellen Sie Ihre technische Frage an Gemini...")).toBeInTheDocument();
    expect(screen.getByText(/Guten Tag! Ich bin der Avenqo Trading AI Marktanalyst/i)).toBeInTheDocument();
    unmountDe();

    // 5. Test Japanese
    const { unmount: unmountJa } = render(
      <TradingGeminiChat symbol="BTCUSDT" interval="1h" locale="ja" />
    );
    expect(screen.getByText("Trading AI アシスタント")).toBeInTheDocument();
    expect(screen.getByText("専門的な質問：")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Geminiにテクニカル分析の質問をする...")).toBeInTheDocument();
    expect(screen.getByText(/Google Geminiを搭載したAvenqo Trading AIマーケットアナリストです/i)).toBeInTheDocument();
    unmountJa();

    // 6. Test Arabic
    const { unmount: unmountAr } = render(
      <TradingGeminiChat symbol="ETHUSDT" interval="1h" locale="ar" />
    );
    expect(screen.getByText("مساعد التداول بالذكاء الاصطناعي")).toBeInTheDocument();
    expect(screen.getByText("أسئلة فنية متخصصة:")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("اطرح سؤالك الفني على جيميني...")).toBeInTheDocument();
    expect(screen.getByText(/أنا محلل السوق Avenqo Trading AI المدعوم بتقنية Google Gemini/i)).toBeInTheDocument();
    unmountAr();
  });
});
