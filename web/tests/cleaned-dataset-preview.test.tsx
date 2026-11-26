import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CleanedDatasetPreview } from "@/components/data/cleaned-dataset-preview";
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
it("renders server-cleaned rows with the preview limit and prints the document", async () => {
  const request = vi.fn(async (input: RequestInfo | URL) => String(input).includes("/rows?")
    ? Response.json({ rows: [{ Product: "<script>unsafe</script>", Sales: 123.45 }], total: 250, preview_snapshot: "a".repeat(64) })
    : new Response(null, { status: 404 }));
  vi.stubGlobal("fetch", request);
  const print = vi.spyOn(window, "print").mockImplementation(() => {});
  const close = vi.fn();
  render(<CleanedDatasetPreview datasetId="chosen" name="Sales.xlsx" isFr={false} onClose={close} />);
  expect(await screen.findByRole("cell", { name: "<script>unsafe</script>" })).toBeVisible();
  expect(screen.getByRole("dialog")).toHaveTextContent("1 / 250 rows shown");
  expect(request.mock.calls.some(([url]) => String(url) === "/api/v1/datasets/chosen/rows?limit=100&offset=0")).toBe(true);
  expect(document.querySelectorAll("script")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Print / PDF" }));
  expect(print).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(close).toHaveBeenCalledOnce();
});
