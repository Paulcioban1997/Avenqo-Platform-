import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SecurityView } from "@/components/security/security-view";
import { ModulesView } from "@/components/common/modules-view";
import { BillingView } from "@/components/billing/billing-view";
import { LocaleProvider } from "@/lib/i18n/locale-context";

vi.mock("@/lib/session-context", () => ({ useSession: () => ({ identity: { user: { role: "owner" }, company: { id: "company" } } }) }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("revokes another session and reloads the authoritative list", async () => {
  let revoked = false;
  const fetch = vi.fn(async (url, init) => {
    if (init?.method === "DELETE") { revoked = true; return new Response(null, { status: 204 }); }
    if (String(url).endsWith("/overview")) return Response.json({ email_verified: true, role: "owner", mfa_supported: true, mfa_enabled: false });
    if (String(url).includes("/audit") || String(url).includes("/support-access") || String(url).endsWith("/login-history")) return Response.json([]);
    return Response.json([{ id: "current", current: true, created_at: "2026-10-10T12:00:00Z", expires_at: "2026-11-10T12:00:00Z" },
      ...revoked ? [] : [{ id: "other", current: false, created_at: "2026-10-09T12:00:00Z", expires_at: "2026-11-09T12:00:00Z" }]]);
  });
  vi.stubGlobal("fetch", fetch);
  render(<LocaleProvider><SecurityView /></LocaleProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Révoquer" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Révoquer" })).not.toBeInTheDocument());
  expect(fetch.mock.calls.some(([url, init]) => url === "/api/v1/security/sessions/other" && init.method === "DELETE")).toBe(true);
  expect(screen.getByRole("button", { name: "Générer une clé" })).toBeInTheDocument();
});

it("unselected modules link to selection rather than the operational module", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ plan_code: "base", module_limit: 2, active_modules: ["crm", "voice"], modules: [
    { key: "crm", display_name: "CRM IA", active: true, state: "active" },
    { key: "voice", display_name: "Voice IA", active: true, state: "active" },
    { key: "retail", display_name: "Retail IA", active: false, state: "limit_reached" },
  ] })));
  render(<LocaleProvider><ModulesView /></LocaleProvider>);
  await screen.findByText("Retail IA");
  expect(screen.getByRole("link", { name: "Gérer ma sélection" })).toHaveAttribute("href", "/settings");
  expect(screen.getAllByRole("link", { name: "Ouvrir le module" }).map(a => a.getAttribute("href"))).toEqual(["/crm", "/voice"]);
  expect(screen.queryByRole("link", { name: "Retail IA" })).not.toBeInTheDocument();
});

it("failed billing requests show an error instead of fabricated plans or packs", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));
  render(<LocaleProvider><BillingView /></LocaleProvider>);
  await screen.findByRole("alert");
  expect(screen.queryByText("Base")).not.toBeInTheDocument();
  expect(screen.queryByText("Pack Découverte")).not.toBeInTheDocument();
  expect(screen.queryByText("2026-09")).not.toBeInTheDocument();
});
