import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SelectedDocumentInvoices } from "@/components/accounting/selected-document-invoices";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("shows original invoice evidence without inventing currency or posting balances", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ documents: [{
    dataset_id: "selected", name: "selected.xlsx", status: "read", extraction: { invoices: [{
      vendor: "Example Transport", issue_date: "2026-11-22", sheet_name: "Invoice", description: "Freight",
      currency: null, math_verified: true,
      total_amount: { amount: "1250.50", amount_formatted_fr: "1 250,50", cell_ref: "Invoice!B4" },
    }] },
  }] })));
  render(<SelectedDocumentInvoices isFr />);
  expect(await screen.findByText(/1 250,50/)).toHaveTextContent("devise non spécifiée");
  expect(screen.getByText(/Invoice!B4/)).toBeInTheDocument();
  expect(screen.getByText(/exclus des soldes comptabilisés/)).toBeInTheDocument();
});

it("shows a failed read as an error instead of a zero invoice balance", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("unavailable", { status: 503 })));
  render(<SelectedDocumentInvoices isFr />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Aucun montant n’a été supposé");
  expect(screen.queryByText(/0,00/)).not.toBeInTheDocument();
});
