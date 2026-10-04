import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/lib/session-context";
import { AvenqoCopilot, type AvenqoCopilotProps } from "@/components/shell/avenqo-copilot";
import { DashboardView } from "@/components/dashboard/dashboard-view";
import { ConnectionsView } from "@/components/connections/connections-view";
import { CRMView } from "@/components/crm/crm-view";
import { RetailIntelligenceView } from "@/components/retail/retail-intelligence-view";
import { PrivacyContent, TrustCenterContent, TrustSections } from "@/components/trust-sections";
import { TRUST_COPY } from "@/lib/i18n/translations/trust";
import { CreditMeter } from "@/components/shell/credit-meter";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
import { LocaleProvider, useLocale } from "@/lib/i18n/locale-context";
import { creditBalanceViewModel } from "@/lib/credit-balance";
import { LOCALES } from "@/lib/i18n/locales";
import { getTranslations } from "@/lib/i18n/dictionary";
import { BUSINESS_HOURS_COPY } from "@/lib/i18n/business-hours-copy";
import { BusinessHoursSettings } from "@/components/crm/business-hours-settings";
import { CRMKpiCards } from "@/components/crm/crm-kpi-cards";
import { metricText, currencyText, dateText } from "@/components/crm/crm-format";

vi.mock("next/navigation", () => ({ usePathname: () => "/retail" }));

function TestCopilot(props: AvenqoCopilotProps) {
  return <SessionProvider><AvenqoCopilot {...props} /></SessionProvider>;
}

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

describe("public trust content", () => {
  it("does not label unverified Shopify credentials as connected", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input) => {
      const path = String(input);
      const body = path.includes("/connectors/connections") ? [{ id: "test-shopify", provider: "shopify", status: "ERROR", connection_status: "CONNECTING", is_active: true, display_name: "Unverified shop", external_account_id: "test.myshopify.com" }] : [];
      return new Response(JSON.stringify(body), { status: 200 });
    }));
    render(<LocaleProvider><ConnectionsView /></LocaleProvider>);
    await screen.findByText("ERROR");
    expect(screen.queryByText(getAppTranslations("fr").integrations.statusConnected)).not.toBeInTheDocument();
  });
  it("shows the Shopify-returned merchant identity after verified setup", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input) => {
      const body = String(input).includes("/connectors/connections") ? [{ id: "verified-test", provider: "shopify", status: "READY", connection_status: "CONNECTED", display_name: "Verified merchant identity", external_account_id: "verified.myshopify.com" }] : [];
      return new Response(JSON.stringify(body), { status: 200 });
    }));
    render(<LocaleProvider><ConnectionsView /></LocaleProvider>);
    expect((await screen.findAllByText("Verified merchant identity")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("verified.myshopify.com")).length).toBeGreaterThan(0);
  });
  it("rejects invalid numeric/date formatting rather than fabricating metrics", () => {
    for (const value of [null, undefined, NaN, Infinity, "12"]) expect(metricText(value, "fr", "unavailable")).toBe("unavailable");
    expect(currencyText(12, null, "ar", "unavailable")).toBe("unavailable");
    expect(dateText("invalid", "ar", "unavailable")).toBe("unavailable");
    expect(metricText(0, "en", "unavailable")).toBe("0");
  });
  it("shows CRM loading state without presenting fabricated numeric values", () => {
    render(<LocaleProvider><CRMKpiCards kpis={{}} isLoading t={getAppTranslations("fr")} /></LocaleProvider>);
    expect(screen.getAllByText(getAppTranslations("fr").crm.calendar.loadingAppointments)).toHaveLength(4);
  });
  it("renders unavailable CRM metrics without inventing zeros", () => {
    render(<LocaleProvider><CRMKpiCards kpis={{ active_clients: null, appointments_this_month: undefined, total_revenue_generated: null }} t={getAppTranslations("fr")} /></LocaleProvider>);
    expect(screen.getAllByText(getAppTranslations("fr").common.insufficientData)).toHaveLength(4);
  });
  it("preserves legitimate authenticated zero CRM metrics", () => {
    render(<LocaleProvider><CRMKpiCards kpis={{ active_clients: 0, appointments_this_month: 0, attendance_rate_percent: 0, total_revenue_generated: 0, currency: "CAD" }} t={getAppTranslations("fr")} /></LocaleProvider>);
    expect(screen.queryByText(getAppTranslations("fr").common.insufficientData)).not.toBeInTheDocument();
  });
  it("loads and saves tenant business hours without losing closed days", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.endsWith("/employees")) return new Response("[]", { status: 200 });
      if (init?.method === "PUT") {
        expect(JSON.parse(String(init.body)).hours.monday).toEqual([{ open: "09:00", close: "17:00" }]);
        return new Response("{}", { status: 200 });
      }
      return new Response(JSON.stringify({ timezone: "America/Toronto", hours: {} }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<LocaleProvider><BusinessHoursSettings /></LocaleProvider>);
    await waitFor(() => expect(screen.getByDisplayValue("America/Toronto")).toBeEnabled());
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", { name: getAppTranslations("fr").crm.actions.save }));
    await waitFor(() => expect(fetchMock.mock.calls.some((call) => call[1]?.method === "PUT")).toBe(true));
  });
  it("has business-hours labels in every canonical locale", () => {
    expect(Object.keys(BUSINESS_HOURS_COPY).sort()).toEqual(LOCALES.map((item) => item.code).sort());
    for (const labels of Object.values(BUSINESS_HOURS_COPY)) expect(labels.every((label) => label.length > 0)).toBe(true);
  });
  beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", class {
      observe() {}
      unobserve() {}
      disconnect() {}
    });
  });

  it("has complete qualified trust and privacy content in all 44 locales", () => {
    expect(Object.keys(TRUST_COPY).sort()).toEqual(LOCALES.map((locale) => locale.code).sort());
    for (const locale of LOCALES) {
      const content = getTranslations(locale.code).trust;
      expect(content).toBe(TRUST_COPY[locale.code]);
      expect(content.cards).toHaveLength(6);
      expect(content.principles).toHaveLength(4);
      expect(content.data).toHaveLength(7);
      expect(content.research[2]).toContain("LawZero");
      expect(content.research[2]).toContain("Yoshua Bengio");
      const strings = Object.values(content).flat(2);
      expect(strings.every((value) => typeof value === "string" && value.trim().length > 0)).toBe(true);
      expect(strings.join(" ")).not.toMatch(/SOC\s*2|ISO\s*27001|HIPAA|GDPR|AES-256|TLS\s*1\.3|Scientist AI/i);
      if (!["en", "en-GB"].includes(locale.code)) {
        expect(content.heading).not.toBe(TRUST_COPY.en.heading);
        expect(content.research[2]).not.toBe(TRUST_COPY.en.research[2]);
      }
    }
  });

  it.each(["en", "fr", "ar"] as const)("renders six trust cards and four principles in %s", async (locale) => {
    window.localStorage.setItem("avenqo-locale", locale);
    const content = TRUST_COPY[locale];
    const { container } = render(<LocaleProvider><TrustSections /></LocaleProvider>);
    expect(await screen.findByRole("heading", { name: content.heading })).toBeInTheDocument();
    expect(container.querySelectorAll(".trust-grid article")).toHaveLength(6);
    expect(container.querySelectorAll(".principle-grid article")).toHaveLength(4);
    expect(screen.getByText(content.research[2])).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "LawZero" })).toHaveAttribute("href", "https://lawzero.org/");
    expect(screen.getByRole("link", { name: content.center })).toHaveAttribute("href", "/trust");
    expect(document.documentElement.dir).toBe(locale === "ar" ? "rtl" : "ltr");
  });

  it("renders localized Privacy and Trust Center without obsolete guarantees", () => {
    window.localStorage.setItem("avenqo-locale", "en");
    const { container } = render(<LocaleProvider><PrivacyContent /><TrustCenterContent /></LocaleProvider>);
    expect(screen.getByRole("heading", { level: 1, name: "Privacy" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Trust Center" })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/AES-256|TLS 1\.3|\bSOC\b|ISO 27001|30 days|6 years/i);
    expect(screen.getAllByRole("link", { name: "Contact us" }).every((link) => link.getAttribute("href") === "/contact")).toBe(true);
  });
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
  it("does not claim there are no CRM appointments before the read completes", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<LocaleProvider><CRMView /></LocaleProvider>);
    expect(screen.getByRole("status")).toHaveTextContent("Chargement");
    expect(screen.queryByText("Aucun rendez-vous")).not.toBeInTheDocument();
  });

  it("reports a failed CRM read instead of displaying zero KPIs", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })));
    render(<LocaleProvider><CRMView /></LocaleProvider>);
    expect(await screen.findByRole("alert")).toHaveAttribute("data-error-category", "backend_error");
    expect(screen.queryByText("REVENUS GÉNÉRÉS")).not.toBeInTheDocument();
  });

  it("keeps Connections in a loading state instead of claiming the dataset is absent", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<LocaleProvider><ConnectionsView /></LocaleProvider>);
    expect(screen.getByRole("status")).toHaveTextContent("Chargement");
    expect(screen.queryByText(getAppTranslations("fr").integrations.noUploadedRetailSources)).not.toBeInTheDocument();
  });

  it("reports a failed Connections read instead of an empty source list", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })));
    render(<LocaleProvider><ConnectionsView /></LocaleProvider>);
    expect(await screen.findByRole("alert")).toHaveAttribute("data-error-category", "backend_error");
    expect(screen.queryByText(getAppTranslations("fr").integrations.noUploadedRetailSources)).not.toBeInTheDocument();
  });

  it("does not report a disconnected source while its status is loading", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<LocaleProvider><RetailIntelligenceView /></LocaleProvider>);
    expect(screen.queryByText("Déconnecté")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Chargement");
  });

  it("renders products with an unknown stock count without crashing the page", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return Response.json({ user: { id: "test-user" }, company: { id: "test-tenant", name: "Test tenant", subscription_plan: "base" } });
      if (url.endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: 6500 });
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
      if (url.endsWith("/sales/summary?period=last_30_days")) {
        return Response.json({ currency: "CAD", summary: null, forecast: null });
      }
      if (url.endsWith("/recommendations")) return Response.json({ recommendations: [] });
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
    expect(await screen.findByText(/Aucune prévision n’est disponible/i)).toBeInTheDocument();
    expect(screen.queryByText("Modèle Arima-Ensemble v2")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Recommandations" }));
    expect(screen.queryByText(/98 %|98%|15 unités/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/Aucune recommandation n’a été générée/i)).toBeInTheDocument();
  });

  it("renders forecast and recommendation data returned by their tenant APIs", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return Response.json({ user: { id: "test-user" }, company: { id: "test-tenant", name: "Test tenant", subscription_plan: "base" } });
      if (url.endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: 6500 });
      if (url.endsWith("/retail/status")) {
        return Response.json({
          is_connected: true,
          provider: "dataset",
          store_url: null,
          status: "READY",
          last_synced_at: null,
          records_count: 3,
          product_count: 1,
          order_count: 1,
          customer_count: 1,
        });
      }
      if (url.endsWith("/retail/products?limit=100")) return Response.json({ products: [] });
      if (url.endsWith("/retail/orders?limit=100")) return Response.json({ orders: [] });
      if (url.endsWith("/retail/customers?limit=100")) return Response.json({ customers: [] });
      if (url.endsWith("/retail/inventory?limit=100")) return Response.json({ inventory: [], anomalies: [] });
      if (url.endsWith("/sales/summary?period=last_30_days")) {
        return Response.json({
          currency: "CAD",
          summary: { revenue: 500, orders: 3 },
          forecast: {
            method: "historical_weekly_mean",
            granularity: "week",
            forecasted_total: 400,
            points: [
              { period: "Week A", value: 180 },
              { period: "Week B", value: 220 },
            ],
          },
        });
      }
      if (url.endsWith("/recommendations")) {
        return Response.json({ recommendations: [{
          id: "recommendation-1",
          title: "Review the seasonal stock plan",
          explanation: "The active sales model detected a change in demand.",
          suggested_action: "Review the next purchase order",
          action_route: null,
        }] });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(
      <LocaleProvider>
        <RetailIntelligenceView defaultTab="forecasts" />
      </LocaleProvider>,
    );

    expect(await screen.findByText("Moyenne historique hebdomadaire")).toBeInTheDocument();
    expect(screen.getByText("Week A")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Recommandations" }));
    expect(await screen.findByText("Review the seasonal stock plan")).toBeInTheDocument();
    expect(screen.getByText(/Review the next purchase order/)).toBeInTheDocument();
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
      if (url.endsWith("/auth/me")) return Response.json({ user: { id: "test-user" }, company: { id: "test-tenant", name: "Test tenant", subscription_plan: "base" } });
      if (url.endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: 6500 });
      if (url.endsWith("/retail/sources")) return new Response("[]", { status: 200 });
      if (url.endsWith("/ai/chat/conversations")) return Response.json({ id: "same-conversation" });
      if (url.endsWith("/ai/voice/sessions")) return Response.json({ id: "voice-session" });
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(<LocaleProvider><TestCopilot isOpen onClose={vi.fn()} activeRoute="/retail" t={getAppTranslations("fr")} /></LocaleProvider>);
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
      if (url.endsWith("/auth/me")) return Response.json({ user: { id: "test-user" }, company: { id: "test-tenant", name: "Test tenant", subscription_plan: "base" } });
      if (url.endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: 6500 });
      requests.push(url);
      if (url.endsWith("/retail/sources")) return new Response("[]", { status: 200 });
      if (url.endsWith("/ai/chat/conversations")) return Response.json({ id: "same-conversation" });
      if (url.endsWith("/ai/voice/sessions")) return Response.json({ id: "voice-session", conversation_id: "same-conversation" });
      if (url.endsWith("/stream-ticket")) return Response.json({ ticket: "short-ticket", realtime: true });
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(<LocaleProvider><TestCopilot isOpen onClose={vi.fn()} activeRoute="/retail" t={getAppTranslations("en")} /></LocaleProvider>);
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
      if (url.endsWith("/auth/me")) return Response.json({ user: { id: "test-user" }, company: { id: "test-tenant", name: "Test tenant", subscription_plan: "base" } });
      if (url.endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: 6500 });
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
        <TestCopilot
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
      if (url.endsWith("/auth/me")) return Response.json({ user: { id: "test-user" }, company: { id: "test-tenant", name: "Test tenant", subscription_plan: "base" } });
      if (url.endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: 6500 });
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
        <TestCopilot
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

it("shows a Dashboard backend failure instead of a valid empty dataset", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/auth/me")) return Response.json({ user: { id: "test-user", first_name: "Alex" }, company: { id: "test-tenant", name: "Test tenant", subscription_plan: "base" } });
    if (url.endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: 6000 });
    if (url.includes("/dashboard?")) return Response.json({ error: { message: "Dashboard service unavailable" } }, { status: 503 });
    return Response.json([]);
  }));
  render(<LocaleProvider><SessionProvider><DashboardView /></SessionProvider></LocaleProvider>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Dashboard service unavailable");
  expect(screen.queryByText("Mon espace")).not.toBeInTheDocument();
});
