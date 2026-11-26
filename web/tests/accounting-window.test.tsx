import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AccountingView } from "@/components/accounting/accounting-view";

vi.mock("@/lib/i18n/locale-context", () => ({ useLocale: () => ({ locale: "en" }) }));

it("loads the remaining invoice window without exceeding either endpoint's limit", async () => {
  const requests: string[] = [];
  vi.stubGlobal("fetch", async (path: string) => {
    requests.push(path);
    const url = new URL(path, "https://avenqo.test");
    const limit = Number(url.searchParams.get("limit"));
    if (limit > 200) return new Response(null, { status: 422 });
    if (url.searchParams.get("document_scope") === "true") return Response.json([]);
    if (url.pathname.endsWith("/invoices")) {
      return Response.json(Array.from({ length: limit }, (_, index) => ({
        id: String(index),
        invoice_number: `INV-${index}`,
        invoice_type: "receivable",
        issue_date: "2026-11-25",
        currency: "CAD",
        total_amount: 100,
      })));
    }
    return Response.json(url.pathname.endsWith("/transactions") ? [] : {});
  });

  try {
    render(<AccountingView />);
    fireEvent.click(await screen.findByRole("button", { name: "Load more invoices (+50)" }));
    await waitFor(() => expect(screen.getByText(/200 loaded invoice/)).toBeVisible());
    expect(screen.queryByRole("button", { name: /load more invoices/i })).not.toBeInTheDocument();
    expect(requests).toContain("/api/v1/accounting/invoices?document_scope=true&limit=200");
    expect(requests.filter(path => /\/(invoices|transactions)\?/.test(path) && !path.includes("document_scope=true"))).toEqual([
      "/api/v1/accounting/invoices?limit=150",
      "/api/v1/accounting/transactions?limit=150",
      "/api/v1/accounting/invoices?limit=200",
      "/api/v1/accounting/transactions?limit=200",
    ]);
  } finally {
    vi.unstubAllGlobals();
  }
});
