import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarketingView } from "../src/components/marketing/marketing-view";
vi.mock("@/lib/i18n/locale-context", () => ({ useLocale: () => ({ locale: "fr" }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function submit() {
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Préparer une campagne pour notre entreprise" } });
  fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
}
describe("Marketing results and failures", () => {
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
