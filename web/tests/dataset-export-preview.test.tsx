import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { DatasetExportMenu } from "@/components/data/dataset-export-menu";

it("does not offer a filtered export when the visible preview has no rows", async () => {
  const request = vi.fn(async () => new Response(null, { status: 404 }));
  vi.stubGlobal("fetch", request);
  try {
    render(<DatasetExportMenu datasetId="dataset" datasetName="Ventes" previewSnapshot="fixture" previewRowIndices={[]} />);
    fireEvent.click(screen.getByRole("button", { name: /export|télécharg/i }));
    const unavailable = await screen.findByRole("button", { name: /aperçu filtré/i });
    expect(unavailable).toBeDisabled();
    fireEvent.click(unavailable);
    expect(request.mock.calls).toHaveLength(1);
  } finally {
    vi.unstubAllGlobals();
  }
});
