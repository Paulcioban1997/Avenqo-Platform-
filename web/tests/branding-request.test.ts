import { afterEach, expect, it, vi } from "vitest";
import { apiFetch } from "@/lib/api-request";

afterEach(() => { vi.unstubAllGlobals(); });

it("sends a JSON branding body even when the caller omits the content type", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  await apiFetch("/api/v1/onboarding/branding", {
    method: "PUT",
    body: JSON.stringify({ theme_id: "midnight_gold", primary_color: "#D97706" }),
  });
  const headers = new Headers(fetchMock.mock.calls[0][1].headers);
  expect(headers.get("content-type")).toBe("application/json");
});
