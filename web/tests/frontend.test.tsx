import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AvenqoCopilot } from "@/components/shell/avenqo-copilot";
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

describe("Copilot production response", () => {
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
