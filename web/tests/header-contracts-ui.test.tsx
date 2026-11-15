import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ContractsView } from "@/components/settings/contracts-view";
import { CompactStepper } from "@/components/ui/compact-stepper";
import { GlobalSourceSelector } from "@/components/shell/global-source-selector";
import { LocaleProvider } from "@/lib/i18n/locale-context";
import { SessionProvider } from "@/lib/session-context";
import { localeKeyCoverage } from "@/lib/i18n/locale-coverage";
import { CONTRACTS_UI_EXPLICIT } from "@/lib/i18n/contracts-ui-copy";
import { privateLicenseRequiredForPlan } from "@/lib/contracts/private-license";
import { LOCALES } from "@/lib/i18n/locales";
import { SOURCE_SELECTOR_COPY } from "@/lib/i18n/source-selector-copy";

vi.mock("next/image", () => ({ default: ({ alt }: { alt: string }) => <img alt={alt} /> }));
vi.mock("next/navigation", () => ({ usePathname: () => "/settings/contracts", useRouter: () => ({ push: () => undefined }) }));
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

describe("header and contracts UI", () => {
  it("reports honest key coverage for all 44 locales", () => {
    const report = localeKeyCoverage();
    expect(LOCALES).toHaveLength(44);
    for (const catalog of report) {
      expect(catalog.localeCount).toBe(44);
      expect(catalog.explicitLocales).toHaveLength(4);
      expect(catalog.missingLocales).toHaveLength(40);
      expect(catalog.explicitKeySlots).toBe(4 * catalog.keyCount);
      expect(catalog.missingKeySlots).toBe(40 * catalog.keyCount);
    }
    expect(report.find((item) => item.name === "contractsUi")?.keyCount).toBeGreaterThan(40);
    expect(report.find((item) => item.name === "workspaceChrome")?.keyCount).toBeGreaterThan(5);
    const contracts = report.find((item) => item.name === "contractsUi");
    expect(contracts?.explicitLocales.sort()).toEqual(["en", "en-GB", "fr", "fr-FR"]);
    expect(Object.keys(CONTRACTS_UI_EXPLICIT.fr || {})).toEqual(Object.keys(CONTRACTS_UI_EXPLICIT.en || {}));
  });

  it("does not require the private license for an ordinary SaaS plan", () => {
    expect(privateLicenseRequiredForPlan("Base")).toBe(false);
    expect(privateLicenseRequiredForPlan("Professional")).toBe(false);
    expect(privateLicenseRequiredForPlan("Enterprise")).toBe(false);
    expect(privateLicenseRequiredForPlan("")).toBe(false);
    expect(privateLicenseRequiredForPlan("Private server")).toBe(true);
    expect(privateLicenseRequiredForPlan("on-prem dedicated")).toBe(true);
  });

  it("truncates a long dataset name and keeps it available to assistive tech", async () => {
    const longName = "Superstore-utf8.csv";
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/auth/me")) return Response.json({ user: { id: "user", permissions: ["data:read"] }, company: { id: "tenant", name: "Tenant" } });
      if (path.endsWith("/ai-credits")) return Response.json({});
      if (path.endsWith("/sources/context")) {
        return Response.json({
          state: "READY",
          source_type: "dataset",
          source_id: "file-test",
          sources: [{ source_type: "dataset", source_id: "file-test", dataset_id: "file-test", display_name: longName, status: "READY", enabled: true }],
        });
      }
      return Response.json([]);
    }));
    render(<LocaleProvider><SessionProvider><GlobalSourceSelector /></SessionProvider></LocaleProvider>);
    const button = await screen.findByRole("button", { name: new RegExp(SOURCE_SELECTOR_COPY.fr[0]) });
    expect(button.querySelector(".truncate")?.textContent).toContain(longName);
    expect(button).toHaveAttribute("title", longName);
    expect(button.getAttribute("aria-label")).toContain(longName);
  });

  it("shows completed, current, blocked and upcoming stepper states", () => {
    render(
      <CompactStepper
        label="Étapes"
        steps={[
          { id: "1", label: "Profil juridique", state: "completed", stateLabel: "Terminé" },
          { id: "2", label: "Bordereau commercial", state: "blocked", stateLabel: "Bloqué" },
          { id: "3", label: "Revue des accords", state: "current", stateLabel: "En cours" },
          { id: "4", label: "Signature sécurisée", state: "upcoming", stateLabel: "À venir" },
        ]}
      />,
    );
    expect(screen.getByRole("button", { name: /Profil juridique/ })).toBeInTheDocument();
    expect(screen.getByText("Bloqué")).toBeInTheDocument();
    expect(screen.getByText("À venir")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Signature sécurisée/ }));
  });

  it("renders contracts without the sandbox banner and keeps the private license optional", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes("/wizard/status")) return Response.json({ current_step: 4 });
      if (path.includes("/legal-profile")) return Response.json({ legal_name: "Acme" });
      if (path.includes("/commercial-order")) return Response.json({ plan_name: "Professional", is_blocked: false, monthly_price: 49.99, currency: "CAD", selected_modules: ["crm"], max_selectable_modules: 5, included_ai_credits: 20000, applicable_taxes: "TPS", renewal_terms: "mensuel" });
      if (path.endsWith("/contracts")) return Response.json([{ id: "license", company_id: "c", contract_type: "PRIVATE_LICENSE", title: "Licence logicielle privée Avenqo", status: "PENDING_SIGNATURE", version: "1.0", language: "fr", signature_mode: null, signatory_name: null, signatory_title: null, signatory_email: null, signed_at: null, sha256_hash: "abc", has_pdf: false }]);
      return Response.json({});
    }));
    render(<LocaleProvider><SessionProvider><ContractsView /></SessionProvider></LocaleProvider>);
    expect(await screen.findByRole("heading", { name: "Contrats et parcours juridique" })).toBeInTheDocument();
    expect(screen.queryByText(/Sandbox Environment Notice|Environnement Bac à Sable/)).not.toBeInTheDocument();
    expect(screen.getByText("Optionnel. Non requis pour un abonnement SaaS standard.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Consulter" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Signer" })).toBeInTheDocument();
  });
});
