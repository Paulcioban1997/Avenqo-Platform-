import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DocumentWorkspace } from "@/components/workspace/document-workspace";
vi.mock("@/lib/i18n/locale-context", () => ({ useLocale: () => ({ locale: "fr" }) }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
it("prepares a reviewable accounting proposal and exposes a printable extraction", async () => {
  const request = vi.fn(async (path: RequestInfo | URL) => Response.json(String(path).endsWith("/accounting-proposal") ? { id: "invoice" } :
    [{ id: "doc", filename: "invoice.pdf", classification: "invoice", extracted_text: "Total 1379.70 CAD", created_at: null }]));
  vi.stubGlobal("fetch", request);
  const print = vi.spyOn(window, "print").mockImplementation(() => {});
  render(<DocumentWorkspace kind="ocr" titleFr="OCR" titleEn="OCR" />);
  fireEvent.click(await screen.findByRole("button", { name: "Préparer en comptabilité" }));
  await screen.findByRole("button", { name: "Proposition préparée — à vérifier" });
  expect(request.mock.calls.some(([path]) => String(path).endsWith("/ocr/documents/doc/accounting-proposal"))).toBe(true);
  expect(screen.getByRole("link", { name: "Voir les documents comptables" })).toHaveAttribute("href", "/accounting#ocr-documents");
  fireEvent.click(screen.getByRole("button", { name: "Aperçu / Imprimer" }));
  expect(screen.getByRole("dialog", { name: "Aperçu des données extraites" })).toHaveTextContent("Total 1379.70 CAD");
  fireEvent.click(screen.getByRole("button", { name: "Imprimer / PDF" }));
  expect(print).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Fermer" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});
