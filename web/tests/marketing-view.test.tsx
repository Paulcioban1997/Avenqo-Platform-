import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarketingView } from "../src/components/marketing/marketing-view";
const session = vi.hoisted(() => ({ tenant: "", revision: 0 }));
vi.mock("@/lib/session-context", () => ({ useSession: () => ({ identity: session.tenant ? { company: { id: session.tenant } } : null, sourceRevision: session.revision }) }));
vi.mock("@/lib/i18n/locale-context", () => ({ useLocale: () => ({ locale: "fr" }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); session.tenant = ""; session.revision = 0; });
function submit() {
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Préparer une campagne pour notre entreprise" } });
  fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
}
describe("Marketing results and failures", () => {
  it("computes its displayed metrics from the actual selected-source response", async () => {
    session.tenant = "alpha";
    const request = vi.fn(async () => ({ ok: true, json: async () => ({ available: true, currency: "CAD",
      source_context: { name: "Superstore-utf8.csv" }, summary: { total_customers: 793, active_customers: 0, purchase_frequency: 6.32, average_customer_value: 2896.85 },
      segments: [{ label: "vip", count: 127 }] }) }));
    vi.stubGlobal("fetch", request); render(<MarketingView />);
    await screen.findByText("793");
    expect(screen.getByRole("status")).toHaveTextContent("Superstore-utf8.csv");
    expect(screen.getByText("127")).toBeVisible();
    expect(screen.getByRole("img", { name: "vip: 127 / 793" })).toBeVisible();
    expect((request.mock.calls as unknown as [string, RequestInit?][])[0][0]).toBe("/api/v1/customers/summary?period=all&page_size=1");
  });
  it("never displays a late response from the previous tenant", async () => {
    session.tenant = "alpha";
    let resolve!: (value: unknown) => void;
    const request = vi.fn().mockImplementationOnce(() => new Promise(r => { resolve = r; }))
      .mockResolvedValue({ ok: true, json: async () => ({ available: false, summary: null, segments: [] }) });
    vi.stubGlobal("fetch", request);
    const { rerender } = render(<MarketingView />);
    session.tenant = "beta"; rerender(<MarketingView />);
    resolve({ ok: true, json: async () => ({ available: true, summary: { total_customers: 987654 }, segments: [] }) });
    await screen.findByText(/Cette analyse n’est pas disponible/, { selector: "p[role=status]" });
    expect(screen.queryByText("987 654")).toBeNull();
  });
  it("does not report CSV failure or invented segmentation before an analysis", () => {
    render(<MarketingView />);
    expect(screen.queryByText(/Ce fichier n.a pas pu être traité/)).toBeNull();
    expect(screen.queryByText(/15\s*%/)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("shows permission refusal as an error, never a generated draft", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 403, json: async () => ({}) })));
    render(<MarketingView />); submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Accès refusé");
    expect(screen.getByRole("link", { name: "Mes modules" })).toHaveAttribute("href", "/workspace/modules");
    expect(screen.queryByText("Brouillon")).toBeNull();
    expect(screen.getByRole("button", { name: "Envoyer" })).toBeEnabled();
  });
  it("shows only successful nonempty provider output and clears it on a failed retry", async () => {
    const request = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ output_text: "Texte confirmé", provider: "qa" }) })
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) });
    vi.stubGlobal("fetch", request);
    render(<MarketingView />); submit();
    await screen.findByText("Texte confirmé"); submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("La génération a échoué");
    expect(screen.queryByText("Texte confirmé")).toBeNull();
  });
  it("rejects an empty success response rather than displaying a fake result", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({}) })));
    render(<MarketingView />); submit();
    await screen.findByRole("alert");
    expect(screen.queryByText("Brouillon")).toBeNull();
  });
});
