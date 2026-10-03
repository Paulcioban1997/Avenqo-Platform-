import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AvenqoCopilot } from "@/components/shell/avenqo-copilot";
import { RetailIntelligenceView } from "@/components/retail/retail-intelligence-view";
import { CreditMeter } from "@/components/shell/credit-meter";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { LocaleProvider, useLocale } from "@/lib/i18n/locale-context";
import { creditBalanceViewModel } from "@/lib/credit-balance";
import { LOCALES } from "@/lib/i18n/locales";
import { getTranslations } from "@/lib/i18n/dictionary";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: { children: ReactNode; href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("credit display", () => {
  it("renders remaining credits and updates without a reload", () => {
    const { rerender } = render(
      <CreditMeter
        remaining={6486}
        limit={6500}
        label="Crédits IA"
        upgradeLabel="Changer de plan"
      />,
    );

    expect(screen.getByText(/6[\s,]486 \/ 6[\s,]500/)).toBeInTheDocument();
    expect(screen.queryByText(/0 \/ 6[\s,]500/)).not.toBeInTheDocument();

    rerender(
      <CreditMeter
        remaining={6485}
        limit={6500}
        label="Crédits IA"
        upgradeLabel="Changer de plan"
      />,
    );
    expect(screen.getByText(/6[\s,]485 \/ 6[\s,]500/)).toBeInTheDocument();
  });

  it("derives Billing remaining, used, and limit from the same ledger payload", () => {
    expect(creditBalanceViewModel({
      monthly_included: 6500,
      monthly_remaining: 6485,
    })).toEqual({ remaining: 6485, used: 15, limit: 6500 });
  });
});

describe("Retail inventory rendering", () => {
  it("renders products with an unknown stock count without crashing the page", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/retail/status")) {
        return Response.json({
          is_connected: true,
          provider: "dataset",
          store_url: null,
          status: "READY",
          last_synced_at: null,
          records_count: 1,
          product_count: 1,
          order_count: 0,
          customer_count: 0,
        });
      }
      if (url.endsWith("/retail/products?limit=100")) return Response.json({ products: [] });
      if (url.endsWith("/retail/orders?limit=100")) return Response.json({ orders: [] });
      if (url.endsWith("/retail/customers?limit=100")) return Response.json({ customers: [] });
      if (url.endsWith("/retail/inventory?limit=100")) {
        return Response.json({
          inventory: [{
            id: "product-1",
            product_name: "Product without stock data",
            sku: "SKU-UNKNOWN",
            stock_quantity: null,
            unit_price: 12,
            status: "unknown",
          }],
          anomalies: [],
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(
      <LocaleProvider>
        <RetailIntelligenceView defaultTab="inventory" />
      </LocaleProvider>,
    );

    expect(await screen.findByText("SKU-UNKNOWN")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Vue d.ensemble/ }));
    expect(screen.queryByText(/\d{2} \/ 100/)).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Prévisions" })[0]);
    expect(await screen.findByText(/prévisions ne sont pas disponibles/i)).toBeInTheDocument();
    expect(screen.queryByText("Modèle Arima-Ensemble v2")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Recommandations" }));
    expect(screen.queryByText(/98 %|98%|15 unités/i)).not.toBeInTheDocument();
  });
});

describe("Copilot production response", () => {
  it("does not pin browser speech recognition to the account or browser locale", async () => {
    const audioContext = {
      resume: vi.fn(async () => undefined),
      close: vi.fn(async () => undefined),
    };
    vi.stubGlobal("AudioContext", class { constructor() { return audioContext; } });
    vi.stubGlobal("navigator", { ...navigator, language: "fr-FR", mediaDevices: undefined });
    const recognitions: Array<{ lang?: string; start: () => void; stop: () => void }> = [];
    vi.stubGlobal("SpeechRecognition", class {
      lang?: string;
      start() {}
      stop() {}
      constructor() { recognitions.push(this); }
    });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/retail/sources")) return new Response("[]", { status: 200 });
      if (url.endsWith("/ai/chat/conversations")) return Response.json({ id: "same-conversation" });
      if (url.endsWith("/ai/voice/sessions")) return Response.json({ id: "voice-session" });
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(<LocaleProvider><AvenqoCopilot isOpen onClose={vi.fn()} activeRoute="/retail" t={getAppTranslations("fr")} /></LocaleProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Start microphone" }));
    await waitFor(() => expect(recognitions).toHaveLength(1));

    expect(recognitions[0].lang).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "Stop microphone" }));
  });

  it("streams microphone PCM and provider audio through the Voice session without an HTTP turn", async () => {
    const playbackStart = vi.fn();
    const playbackClose = vi.fn(async () => undefined);
    const processor = { onaudioprocess: null as ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void) | null,
      connect: vi.fn(), disconnect: vi.fn() };
    const context = {
      sampleRate: 24000, currentTime: 0, destination: {},
      resume: vi.fn(async () => undefined), close: playbackClose,
      createMediaStreamSource: () => ({ connect: vi.fn(), disconnect: vi.fn() }),
      createScriptProcessor: () => processor,
      createBuffer: (_channels: number, count: number) => ({ getChannelData: () => new Float32Array(count), duration: count / 24000 }),
      createBufferSource: () => ({ connect: vi.fn(), start: playbackStart, buffer: null }),
    };
    vi.stubGlobal("AudioContext", class { constructor() { return context; } });
    const stopTrack = vi.fn();
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] })) },
    });
    const sockets: Array<{ onopen?: () => void; onmessage?: (event: { data: string }) => void;
      onclose?: () => void; sent: string[]; readyState: number; protocols: string[]; close: () => void }> = [];
    vi.stubGlobal("WebSocket", class {
      static OPEN = 1;
      readyState = 1;
      bufferedAmount = 0;
      sent: string[] = [];
      onopen?: () => void;
      onmessage?: (event: { data: string }) => void;
      onclose?: () => void;
      close() { this.onclose?.(); }
      constructor(public url: string, public protocols: string[]) {
        sockets.push(this);
        queueMicrotask(() => this.onopen?.());
      }
      send(value: string) { this.sent.push(value); }
    });
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.endsWith("/retail/sources")) return new Response("[]", { status: 200 });
      if (url.endsWith("/ai/chat/conversations")) return Response.json({ id: "same-conversation" });
      if (url.endsWith("/ai/voice/sessions")) return Response.json({ id: "voice-session", conversation_id: "same-conversation" });
      if (url.endsWith("/stream-ticket")) return Response.json({ ticket: "short-ticket", realtime: true });
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(<LocaleProvider><AvenqoCopilot isOpen onClose={vi.fn()} activeRoute="/retail" t={getAppTranslations("en")} /></LocaleProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Start microphone" }));
    await waitFor(() => expect(processor.onaudioprocess).toBeTruthy());
    sockets[0].onmessage?.({ data: JSON.stringify({ type: "lifecycle", next_audio_sequence: 0 }) });
    processor.onaudioprocess!({ inputBuffer: { getChannelData: () => new Float32Array(2048) } });
    expect(JSON.parse(sockets[0].sent[0])).toMatchObject({ type: "audio", sequence: 0 });
    expect(sockets[0].protocols).toEqual(["avenqo.voice", "ticket.short-ticket"]);
    sockets[0].onmessage?.({ data: JSON.stringify({ type: "audio", format: "pcm16", audio: "AQI=" }) });
    expect(playbackStart).toHaveBeenCalled();
    sockets[0].onmessage?.({ data: JSON.stringify({ type: "lifecycle", status: "interrupted" }) });
    expect(playbackClose).toHaveBeenCalled();
    expect(requests.every((url) => !url.endsWith("/turn"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Stop microphone" }));
    expect(stopTrack).toHaveBeenCalled();
  });

  it("renders grounded Retail values and never CRM fallback values", async () => {
    const answers = [
      "Chiffre d'affaires : 2 297 200,86 CAD. Commandes : 5 009. Clients : 793. AOV : 458,61 CAD. Source : Superstore-utf8-cleaned.csv",
      "Vous avez 5 009 commandes.",
      "Votre chiffre d'affaires total est de 2 297 200,86 CAD.",
    ];
    let messageIndex = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/retail/sources")) {
        return new Response(JSON.stringify([{ source_id: "dataset-1", display_name: "Superstore-utf8-cleaned.csv", enabled: true }]), { status: 200 });
      }
      if (url.endsWith("/ai/chat/conversations")) {
        return new Response(JSON.stringify({ id: "conversation-1" }), { status: 201 });
      }
      if (url.includes("/ai/central/conversations/") && init?.method === "POST") {
        return new Response(JSON.stringify({ answer: answers[messageIndex++], status: "success", grounded_source: "Superstore-utf8-cleaned.csv" }), { status: 200 });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(
      <LocaleProvider>
        <AvenqoCopilot
          isOpen
          onClose={vi.fn()}
          activeRoute="/retail"
          t={getAppTranslations("fr")}
        />
      </LocaleProvider>,
    );

    const input = screen.getByPlaceholderText(/posez une question/i);
    const send = screen.getByRole("button", { name: /envoyer/i });

    fireEvent.change(input, { target: { value: "Donne-moi les chiffres de mes ventes" } });
    fireEvent.click(send);
    await waitFor(() => expect(screen.getByText(/2 297 200,86 CAD/)).toBeInTheDocument());
    expect(screen.getByText(/5 009/)).toBeInTheDocument();
    expect(screen.getByText(/793/)).toBeInTheDocument();
    expect(screen.getByText(/458,61 CAD/)).toBeInTheDocument();
    expect(screen.getAllByText(/Superstore-utf8-cleaned\.csv/).length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/11 clients|1 rendez-vous|0 CAD/i)).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: "Combien de commandes ai-je ?" } });
    fireEvent.click(send);
    await waitFor(() => expect(screen.getByText("Vous avez 5 009 commandes.")).toBeInTheDocument());

    fireEvent.change(input, { target: { value: "Quel est mon chiffre d'affaires total ?" } });
    fireEvent.click(send);
    await waitFor(() => expect(screen.getByText(/Votre chiffre d'affaires total est de 2 297 200,86 CAD/)).toBeInTheDocument());
  });

  it("reuses the same idempotency key when retrying the same request", async () => {
    const requestKeys: string[] = [];
    let messageAttempts = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/retail/sources")) {
        return new Response("[]", { status: 200 });
      }
      if (url.endsWith("/ai/chat/conversations")) {
        return new Response(JSON.stringify({ id: "retry-conversation" }), { status: 201 });
      }
      if (url.includes("/ai/central/conversations/") && init?.method === "POST") {
        requestKeys.push(new Headers(init.headers).get("Idempotency-Key") || "");
        messageAttempts += 1;
        if (messageAttempts === 1) return new Response("{}", { status: 503 });
        return new Response(JSON.stringify({ answer: "Done", status: "success" }), { status: 200 });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(
      <LocaleProvider>
        <AvenqoCopilot
          isOpen
          onClose={vi.fn()}
          activeRoute="/retail"
          t={getAppTranslations("en")}
        />
      </LocaleProvider>,
    );

    const input = screen.getByPlaceholderText(/ask anything/i);
    const send = screen.getByRole("button", { name: /send/i });
    fireEvent.change(input, { target: { value: "Summarize today's sales" } });
    fireEvent.click(send);
    await waitFor(() => expect(messageAttempts).toBe(1));
    fireEvent.change(input, { target: { value: "Summarize today's sales" } });
    fireEvent.click(send);
    await waitFor(() => expect(screen.getByText("Done")).toBeInTheDocument());

    expect(requestKeys).toHaveLength(2);
    expect(requestKeys[0]).toBeTruthy();
    expect(requestKeys[1]).toBe(requestKeys[0]);
  });
});

describe("locale persistence", () => {
  function LocaleProbe() {
    const { locale, setLocale } = useLocale();
    return <button onClick={() => setLocale(locale === "fr" ? "en" : "fr")}>{locale}</button>;
  }

  it("persists FR and EN through provider recreation", async () => {
    const first = render(<LocaleProvider><LocaleProbe /></LocaleProvider>);
    await waitFor(() => expect(first.getByRole("button")).toHaveTextContent("fr"));
    fireEvent.click(first.getByRole("button"));
    await waitFor(() => expect(first.getByRole("button")).toHaveTextContent("en"));
    first.unmount();

    const second = render(<LocaleProvider><LocaleProbe /></LocaleProvider>);
    await waitFor(() => expect(second.getByRole("button")).toHaveTextContent("en"));
    fireEvent.click(second.getByRole("button"));
    await waitFor(() => expect(second.getByRole("button")).toHaveTextContent("fr"));
    second.unmount();

    const third = render(<LocaleProvider><LocaleProbe /></LocaleProvider>);
    await waitFor(() => expect(third.getByRole("button")).toHaveTextContent("fr"));
  });

  it.each(LOCALES)("persists the platform locale $code through provider recreation", async ({ code }) => {
    window.localStorage.setItem("avenqo-locale", code);
    const view = render(<LocaleProvider><LocaleProbe /></LocaleProvider>);
    await waitFor(() => expect(view.getByRole("button")).toHaveTextContent(code));
    view.unmount();

    const recreated = render(<LocaleProvider><LocaleProbe /></LocaleProvider>);
    await waitFor(() => expect(recreated.getByRole("button")).toHaveTextContent(code));
    recreated.unmount();
  });
});

describe("44-locale translation catalog", () => {
  it("loads a complete non-empty catalog for every registered platform locale", () => {
    expect(LOCALES).toHaveLength(44);
    for (const definition of LOCALES) {
      const translations = getTranslations(definition.code);
      expect(translations.common.login, definition.code).toBeTruthy();
      expect(translations.nav.docs, definition.code).toBeTruthy();
      expect(translations.dashboard.greeting, definition.code).toBeTruthy();
      expect(translations.pricing.title, definition.code).toBeTruthy();
      expect(["ltr", "rtl"], definition.code).toContain(definition.direction);
    }
  });
});

describe("authenticated navigation labels", () => {
  it("uses IA consistently in French", () => {
    const { navigation, shell } = getAppTranslations("fr");
    expect([
      navigation.dashboard,
      navigation.retailAi,
      navigation.crmAi,
      navigation.accountingAi,
      navigation.marketingAi,
      navigation.voiceAi,
      navigation.ocrAi,
      navigation.chatbotsAi,
      navigation.agentsAi,
      navigation.connections,
      navigation.dataHub,
      navigation.billing,
      navigation.settings,
      shell.aiCredits,
    ]).toEqual([
      "Tableau de bord", "Retail IA", "CRM IA", "Comptabilité IA",
      "Marketing IA", "Voice IA", "OCR IA", "Chatbots IA", "Agents IA",
      "Connexions", "Données & Nettoyage", "Facturation & Plans",
      "Paramètres", "Crédits IA",
    ]);
  });

  it("uses AI consistently in English", () => {
    const { navigation, shell } = getAppTranslations("en");
    expect([
      navigation.dashboard,
      navigation.retailAi,
      navigation.crmAi,
      navigation.accountingAi,
      navigation.marketingAi,
      navigation.voiceAi,
      navigation.ocrAi,
      navigation.chatbotsAi,
      navigation.agentsAi,
      navigation.connections,
      navigation.dataHub,
      navigation.billing,
      navigation.settings,
      shell.aiCredits,
    ]).toEqual([
      "Dashboard", "Retail AI", "CRM AI", "Accounting AI", "Marketing AI",
      "Voice AI", "OCR AI", "AI Chatbots", "AI Agents", "Connections",
      "Data & Cleaning", "Billing & Plans", "Settings", "AI Credits",
    ]);
  });
});
