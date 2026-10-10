import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
import { SOURCE_SELECTOR_COPY } from "@/lib/i18n/source-selector-copy";
import { RETAIL_ANOMALY_COPY } from "@/lib/i18n/retail-anomaly-copy";
import { VOICE_HEALTH_COPY } from "@/lib/i18n/voice-health-copy";
import { VOICE_NUMBER_COPY, VOICE_SELECTION_COPY, VOICE_NUMBER_TYPE_COPY } from "@/lib/i18n/voice-number-copy";
import { GlobalSourceSelector } from "@/components/shell/global-source-selector";
import { CRMCopilotPanel } from "@/components/crm/crm-copilot-panel";
import { SettingsView } from "@/components/settings/settings-view";
import { VoiceModuleView } from "@/components/settings/voice-module-view";

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
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("public trust content", () => {
  it("has source-selector labels in all 44 canonical catalogs", () => {
    expect(Object.keys(SOURCE_SELECTOR_COPY).sort()).toEqual(LOCALES.map(item => item.code).sort());
    expect(Object.keys(RETAIL_ANOMALY_COPY).sort()).toEqual(LOCALES.map(item => item.code).sort());
    expect(Object.keys(VOICE_HEALTH_COPY).sort()).toEqual(LOCALES.map(item => item.code).sort());
    expect(Object.keys(VOICE_NUMBER_COPY).sort()).toEqual(LOCALES.map(item => item.code).sort());
    expect(Object.keys(VOICE_SELECTION_COPY).sort()).toEqual(LOCALES.map(item => item.code).sort());
    expect(Object.keys(VOICE_NUMBER_TYPE_COPY).sort()).toEqual(LOCALES.map(item => item.code).sort());
    for (const copy of Object.values(VOICE_NUMBER_TYPE_COPY)) expect(copy.every(value => value.trim().length > 0)).toBe(true);
    for (const copy of Object.values(VOICE_SELECTION_COPY)) expect(copy.every(value => value.trim().length > 0)).toBe(true);
    for (const copy of Object.values(RETAIL_ANOMALY_COPY)) {
      expect(Object.values(copy).every(value => value.trim().length > 0)).toBe(true);
    }
    for (const copy of Object.values(VOICE_HEALTH_COPY)) {
      expect(Object.values(copy).every(value => value.trim().length > 0)).toBe(true);
    }
    for (const copy of Object.values(VOICE_NUMBER_COPY)) {
      expect(Object.values(copy).every(value => value.trim().length > 0)).toBe(true);
    }
  });
  it("selects real context sources without touching activation or sync", async () => {
    const sources = [{ source_type: "dataset", source_id: "file-test", dataset_id: "file-test", display_name: "Uploaded test", status: "READY", enabled: true }, { source_type: "connector", source_id: "shop-test", dataset_id: "shop-data", display_name: "Verified merchant", provider: "shopify", status: "READY", enabled: true }];
    let selected = "file-test";
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input, init) => {
      const path = String(input); requests.push(path);
      if (path.endsWith("/auth/me")) return Response.json({ user: { id: "user" }, company: { id: "tenant", name: "Tenant" } });
      if (path.endsWith("/ai-credits")) return Response.json({});
      if (path.endsWith("/sources/active")) { selected = JSON.parse(String(init.body)).source_id; return Response.json({}); }
      if (path.endsWith("/sources/context")) return Response.json({ state: "READY", source_type: selected === "file-test" ? "dataset" : "connector", source_id: selected, sources });
      return Response.json(sources);
    }));
    render(<LocaleProvider><SessionProvider><GlobalSourceSelector /></SessionProvider></LocaleProvider>);
    await screen.findByText("Uploaded test");
    fireEvent.click(screen.getByRole("button", { name: SOURCE_SELECTOR_COPY.fr[0] }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: /Verified merchant/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: SOURCE_SELECTOR_COPY.fr[0] })).toHaveTextContent("Verified merchant"));
    expect(requests.some(path => /enabled|sync|disconnect/.test(path))).toBe(false);
  });
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

describe("native Voice module read-only selection", () => {
  const offer = {
    phone_number: "+14386075162", country_code: "CA", region: "PQ", locality: "MONTREAL",
    number_type: "local", is_orderable: true, capabilities: ["voice", "sms", "mms"],
    cost_information: { upfront_cost: "1.00", monthly_cost: "1.00", currency: "USD" },
    regulatory_requirements: [], regulatory_status: "unknown",
  };

  function mockVoice(enabled: boolean, purchaseAllowed = false) {
    const calls: { path: string; method: string }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input, options) => {
      const path = String(input); calls.push({ path, method: options?.method ?? "GET" });
      if (path.endsWith('/auth/me')) return Response.json({ user: { id: 'owner', role: 'owner' }, company: { id: 'voice-tenant', name: 'Voice Company' } });
      if (path.endsWith('/voice/capabilities')) return Response.json({ tenant_id: 'voice-tenant', subscription_plan: 'base', subscription_status: 'active', enabled_modules: enabled ? ['voice', 'retail'] : ['retail'], plan_compatible_modules: ['voice', 'retail'], available_agents: ['retail'], permissions: ['ai:use', 'modules:manage'], locale: 'fr', timezone: 'America/Toronto', authorized_sources: { sources: [] }, language_matrix: LOCALES.map(item => ({ locale: item.code, UI_TRANSLATION_SUPPORTED: true, STT_SUPPORTED: null, LLM_LANGUAGE_SUPPORTED: null, TTS_SUPPORTED: null, LIVE_AUDIO_VALIDATED: false, FULLY_SUPPORTED: false })) });
      if (path.endsWith('/voice/status')) return Response.json({ voice_status: 'NOT_CONFIGURED', business_number: null, call_count: 0, call_minutes: 0, voice_ai_credits_charged: 0, recent_calls: [], data_freshness: { freshness_status: 'SYNCED' } });
      if (path.includes('/voice/numbers/search?')) return Response.json({ offers: [offer] });
      if (path.includes('/voice/numbers/quote?')) return Response.json({ offer, quote_token: 'tenant-scoped-signed-quote', purchase_allowed: purchaseAllowed, expires_in_seconds: 300 });
      if (path.endsWith('/voice/numbers/provision')) return Response.json({ status: 'ACTIVE', number: { id: 'owned-number' } });
      if (path.endsWith('/sources/context')) return Response.json({ state: 'NO_SOURCE_SELECTED', sources: [] });
      if (path.endsWith('/sources')) return Response.json([]);
      return Response.json({});
    }));
    return calls;
  }

  it.each(['fr', 'en', 'ro', 'es'] as const)("searches generic market filters and selects without purchase in %s", async (locale) => {
    window.localStorage.setItem('avenqo-locale', locale);
    const calls = mockVoice(true);
    render(<LocaleProvider><SessionProvider><VoiceModuleView /></SessionProvider></LocaleProvider>);
    await screen.findByRole('button', { name: VOICE_NUMBER_COPY[locale].search });
    fireEvent.change(screen.getByLabelText(VOICE_NUMBER_COPY[locale].country), { target: { value: 'CA' } });
    fireEvent.change(screen.getByLabelText(VOICE_NUMBER_COPY[locale].locality), { target: { value: 'Montreal' } });
    fireEvent.change(screen.getByLabelText(VOICE_SELECTION_COPY[locale][1]), { target: { value: '438' } });
    fireEvent.click(screen.getByRole('button', { name: VOICE_NUMBER_COPY[locale].search }));
    const radio = await screen.findByRole('radio', { name: `${VOICE_SELECTION_COPY[locale][3]} ${offer.phone_number}` });
    fireEvent.click(radio);
    expect(radio).toBeChecked();
    const request = calls.find(item => item.path.includes('/voice/numbers/search?'));
    expect(request?.method).toBe('GET');
    const params = new URL(request!.path, 'https://avenqo.test').searchParams;
    expect(params.get('country_code')).toBe('CA');
    expect(params.get('locality')).toBe('Montreal');
    expect(params.get('area_code')).toBe('438');
    expect(params.has('organization_id')).toBe(false);
    expect(calls.every(item => item.method === 'GET')).toBe(true);
    expect(calls.some(item => /provision|number_orders|reserve|release/.test(item.path))).toBe(false);
    act(() => window.dispatchEvent(new Event('avenqo:session-expired')));
    await waitFor(() => expect(screen.queryByText(offer.phone_number)).not.toBeInTheDocument());
  });

  it("shows configuration without querying inventory for an inactive Voice module", async () => {
    const calls = mockVoice(false);
    render(<LocaleProvider><SessionProvider><VoiceModuleView /></SessionProvider></LocaleProvider>);
    await screen.findByText(VOICE_SELECTION_COPY.fr[0], { selector: 'h2' });
    expect(screen.queryByRole('button', { name: VOICE_NUMBER_COPY.fr.search })).not.toBeInTheDocument();
    expect(calls.some(item => item.path.includes('/voice/numbers/search'))).toBe(false);
    expect(calls.every(item => item.method === 'GET')).toBe(true);
  });

  it("requires a current quote and explicit confirmation before provisioning", async () => {
    window.localStorage.setItem('avenqo-locale', 'en');
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const calls = mockVoice(true, true);
    render(<LocaleProvider><SessionProvider><VoiceModuleView /></SessionProvider></LocaleProvider>);
    await screen.findByRole('button', { name: VOICE_NUMBER_COPY.en.search });
    fireEvent.change(screen.getByLabelText(VOICE_NUMBER_COPY.en.country), { target: { value: 'CA' } });
    fireEvent.click(screen.getByRole('button', { name: VOICE_NUMBER_COPY.en.search }));
    fireEvent.click(await screen.findByRole('radio', { name: `${VOICE_SELECTION_COPY.en[3]} ${offer.phone_number}` }));
    fireEvent.click(screen.getByRole('button', { name: VOICE_SELECTION_COPY.en[0] }));
    await screen.findByText(/300s/);
    const quoteCall = calls.find(item => item.path.includes('/voice/numbers/quote?'));
    expect(quoteCall?.method).toBe('GET');
    expect(calls.some(item => item.path.endsWith('/voice/numbers/provision'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: VOICE_NUMBER_COPY.en.purchase }));
    await waitFor(() => expect(calls.some(item => item.path.endsWith('/voice/numbers/provision'))).toBe(true));
    const purchase = calls.find(item => item.path.endsWith('/voice/numbers/provision'));
    expect(purchase?.method).toBe('POST');
    expect(confirm).toHaveBeenCalledTimes(1);
  });

  it("creates the owner PIN only through authenticated Voice security and clears the masked field", async () => {
    window.localStorage.setItem('avenqo-locale', 'en');
    const calls = mockVoice(true);
    render(<LocaleProvider><SessionProvider><VoiceModuleView /></SessionProvider></LocaleProvider>);
    const input = await screen.findByLabelText('PIN');
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('minLength', '6');
    fireEvent.change(input, { target: { value: '907182' } });
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'TestPassword123!' } });
    fireEvent.submit(input.closest('form')!);
    await waitFor(() => expect(calls.some(call => call.path.endsWith('/voice/auth/pin') && call.method === 'PUT')).toBe(true));
    await waitFor(() => expect(input).toHaveValue(''));
    expect(window.localStorage.getItem('voice-pin')).toBeNull();
    expect(screen.queryByText('907182')).not.toBeInTheDocument();
    expect(calls.some(call => /\/tools\/|\/sessions\//.test(call.path))).toBe(false);
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

  it("uses recorded consumption above the allowance and does not infer it from purchased credits", () => {
    expect(creditBalanceViewModel({ monthly_included: 6500, monthly_remaining: 0, monthly_used: 6563 })).toEqual({ remaining: 0, limit: 6500, used: 6563 });
    expect(creditBalanceViewModel({ monthly_included: 6500, total_remaining: 10000 })).toEqual({ remaining: 10000, limit: 6500, used: null });
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
          anomaly_state: "insufficient_data",
        });
      }
      if (url.endsWith("/sales/summary?period=last_30_days")) {
        return Response.json({ currency: "CAD", summary: null, forecast: null });
      }
      if (url.endsWith("/recommendations")) return Response.json({ recommendation_state: "INSUFFICIENT_DATA", recommendations: [] });
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(
      <LocaleProvider>
        <RetailIntelligenceView defaultTab="inventory" />
      </LocaleProvider>,
    );

    expect(await screen.findByText("SKU-UNKNOWN")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Anomalies" }));
    expect(await screen.findByText(getAppTranslations("fr").common.insufficientData)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Vue d.ensemble/ }));
    expect(screen.queryByText(/\d{2} \/ 100/)).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Prévisions" })[0]);
    expect(await screen.findByText(/Aucune prévision n’est disponible/i)).toBeInTheDocument();
    expect(screen.queryByText("Modèle Arima-Ensemble v2")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Recommandations" }));
    expect(screen.queryByText(/98 %|98%|15 unités/i)).not.toBeInTheDocument();
    expect(await screen.findByText(getAppTranslations("fr").common.insufficientData)).toBeInTheDocument();
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
        return Response.json({ currency: "CAD", recommendation_state: "READY", recommendations: [{
          id: "recommendation-1",
          type: "product_growth",
          severity: "medium",
          title: "product_growth",
          description: "product_revenue_changed",
          metric: "product_revenue",
          period: "last_30_days_vs_previous",
          source: { selection: "connector", provider: "shopify", name: "Avenqo Retail Test" },
          evidence: { current: 120, change_percent: 20 },
          affected_product: { name: "Seasonal item" },
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
    expect(await screen.findByText("Produits: Seasonal item")).toBeInTheDocument();
    expect(screen.getByText("Shopify · Avenqo Retail Test")).toBeInTheDocument();
    expect(screen.queryByText(/product_growth|product_revenue_changed|Review the next purchase order/)).not.toBeInTheDocument();
  });
});

describe("CRM Copilot speech transcription", () => {
  it.each([
    ["fr", ["ça", "ça va", "ça va bien"], "ça va bien"],
    ["en", ["I'm", "I'm doing", "I'm doing well"], "I'm doing well"],
    ["es", ["estoy", "estoy muy", "estoy muy bien"], "estoy muy bien"],
    ["ro", ["sunt", "sunt foarte", "sunt foarte bine"], "sunt foarte bine"],
  ] as const)("replaces interim text and commits one final transcript in %s", async (locale, partials, finalText) => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
    window.localStorage.setItem("avenqo-locale", locale);
    const recognitions: Array<{ onresult?: (event: unknown) => void; start: () => void; stop: () => void }> = [];
    vi.stubGlobal("SpeechRecognition", class {
      onresult?: (event: unknown) => void;
      start() {}
      stop() {}
      constructor() { recognitions.push(this); }
    });

    render(<LocaleProvider><CRMCopilotPanel t={getAppTranslations(locale)} /></LocaleProvider>);
    fireEvent.click(document.querySelector("button[aria-label]")!);
    await waitFor(() => expect(recognitions).toHaveLength(1));

    await act(async () => {
      for (const [index, transcript] of partials.entries()) {
        recognitions[0].onresult?.({
          resultIndex: index === 0 ? 0 : 0,
          results: [{ 0: { transcript }, isFinal: transcript === finalText }],
        });
      }
      recognitions[0].onresult?.({ resultIndex: 0, results: [{ 0: { transcript: finalText }, isFinal: true }] });
    });

    expect(document.querySelector<HTMLInputElement>('input[type="text"]')).toHaveValue(finalText);
  });

  it("preserves words genuinely repeated by the speaker", async () => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
    window.localStorage.setItem("avenqo-locale", "en");
    const recognitions: Array<{ onresult?: (event: unknown) => void }> = [];
    vi.stubGlobal("SpeechRecognition", class {
      onresult?: (event: unknown) => void;
      start() {}
      stop() {}
      constructor() { recognitions.push(this); }
    });
    render(<LocaleProvider><CRMCopilotPanel t={getAppTranslations("en")} /></LocaleProvider>);
    fireEvent.click(document.querySelector("button[aria-label]")!);
    await act(async () => recognitions[0].onresult?.({ resultIndex: 0, results: [{ 0: { transcript: "no no" }, isFinal: true }] }));
    expect(document.querySelector<HTMLInputElement>('input[type="text"]')).toHaveValue("no no");
  });

  it("stops the prior recognition instance when CRM unmounts and ignores stale results after remount", async () => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
    window.localStorage.setItem("avenqo-locale", "fr");
    const recognitions: Array<{ onresult?: (event: unknown) => void; start: () => void; stop: ReturnType<typeof vi.fn>; abort: ReturnType<typeof vi.fn> }> = [];
    vi.stubGlobal("SpeechRecognition", class {
      onresult?: (event: unknown) => void;
      start() {}
      stop = vi.fn();
      abort = vi.fn();
      constructor() { recognitions.push(this); }
    });
    const first = render(<LocaleProvider><CRMCopilotPanel t={getAppTranslations("fr")} /></LocaleProvider>);
    const microphone = () => screen.getByRole("button", { name: "Dicter une commande" });
    fireEvent.click(microphone());
    fireEvent.click(microphone());
    expect(recognitions).toHaveLength(1);
    const staleResult = recognitions[0].onresult;
    first.unmount();
    expect(recognitions[0].abort).toHaveBeenCalledOnce();

    render(<LocaleProvider><CRMCopilotPanel t={getAppTranslations("fr")} /></LocaleProvider>);
    fireEvent.click(microphone());
    expect(recognitions).toHaveLength(2);
    await act(async () => staleResult?.({ resultIndex: 0, results: [{ 0: { transcript: "ancien" }, isFinal: true }] }));
    expect(document.querySelector<HTMLInputElement>('input[type="text"]')).toHaveValue("");
    await act(async () => recognitions[1].onresult?.({ resultIndex: 0, results: [{ 0: { transcript: "nouveau" }, isFinal: true }] }));
    expect(document.querySelector<HTMLInputElement>('input[type="text"]')).toHaveValue("nouveau");
  });

  it("prevents a double Copilot submission and reports a bounded timeout", async () => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
    vi.useFakeTimers();
    window.localStorage.setItem("avenqo-locale", "fr");
    let centralRequests = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/ai/chat/conversations")) return Promise.resolve(Response.json({ id: "crm-conversation" }));
      if (url.includes("/ai/central/conversations/")) {
        centralRequests += 1;
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<LocaleProvider><CRMCopilotPanel t={getAppTranslations("fr")} /></LocaleProvider>);
    const input = document.querySelector<HTMLInputElement>('input[type="text"]')!;
    fireEvent.change(input, { target: { value: "Vérifie la disponibilité demain." } });
    const form = input.closest("form")!;
    await act(async () => {
      fireEvent.submit(form);
      fireEvent.submit(form);
      for (let turn = 0; turn < 8; turn += 1) await Promise.resolve();
    });
    expect(centralRequests).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(45_000); });
    expect(screen.getByRole("alert")).toHaveTextContent(getAppTranslations("fr").copilot.errorPrompt);
    expect(screen.queryByText(/Vérification des disponibilités & exécution/)).not.toBeInTheDocument();
  });

  it("does not display an appointment success claim unless Calendar confirms the tool result", async () => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
    window.localStorage.setItem("avenqo-locale", "fr");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/ai/chat/conversations")) return Response.json({ id: "crm-calendar-conversation" });
      if (url.includes("/ai/central/conversations/")) {
        return Response.json({
          status: "success",
          answer: "Votre rendez-vous a été créé.",
          tool_outcomes: [{ tool: "create_appointment", success: true, confirmed: false }],
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));
    render(<LocaleProvider><CRMCopilotPanel t={getAppTranslations("fr")} /></LocaleProvider>);
    const input = document.querySelector<HTMLInputElement>('input[type="text"]')!;
    fireEvent.change(input, { target: { value: "Crée un rendez-vous demain à 14 h." } });
    fireEvent.submit(input.closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent(getAppTranslations("fr").copilot.errorPrompt);
    expect(screen.queryByText("Votre rendez-vous a été créé.")).not.toBeInTheDocument();
  });
});

describe("Voice settings provisioning safety", () => {
  it("does not search or purchase a phone number when Telnyx is not configured", async () => {
    const paths: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      paths.push(path);
      if (path.endsWith("/auth/me")) return Response.json({ user: { id: "owner", first_name: "Voice", last_name: "Owner", role: "owner" }, company: { id: "tenant", name: "Tenant", subscription_plan: "professional" } });
      if (path.endsWith("/modules/entitlements")) return Response.json({ company_id: "tenant", plan_code: "professional", active_modules: ["voice"], modules: [] });
      if (path.endsWith("/voice/status")) return Response.json({ voice_status: "NOT_CONFIGURED", telnyx_status: "NOT_CONFIGURED", retell_status: "NOT_CONFIGURED", stt_status: "NOT_CONFIGURED", tts_status: "NOT_CONFIGURED", realtime_status: "NOT_CONFIGURED", number_status: "READY_FOR_OWNER_ACTION", data_freshness: { freshness_status: "UNAVAILABLE" } });
      if (path.includes("/voice/auth/pin/status")) return Response.json({ has_pin: false, enabled: false, locked: false, last_digits: null });
      if (path.includes("/voice/auth/audit")) return Response.json({ events: [] });
      if (path.includes("/voice/auth/members")) return Response.json({ members: [] });
      throw new Error(`Unexpected fetch: ${path}`);
    }));

    render(<LocaleProvider><SettingsView /></LocaleProvider>);

    expect(await screen.findByText(getAppTranslations("fr").navigation.voiceAi)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Rechercher des numéros/ })).not.toBeInTheDocument();
    expect(paths.some(path => path.includes("/voice/numbers/search") || path.includes("/voice/numbers/provision"))).toBe(false);
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
      if (url.endsWith("/retail/sources/context")) {
        return Response.json({ state: "READY", source_type: "dataset", source_id: "dataset-1", sources: [{ source_type: "dataset", source_id: "dataset-1", dataset_id: "dataset-1", display_name: "Superstore-utf8-cleaned.csv", status: "READY", enabled: true }] });
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
