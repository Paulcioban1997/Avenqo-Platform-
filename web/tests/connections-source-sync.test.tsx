import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SessionProvider } from "@/lib/session-context";
import { LocaleProvider } from "@/lib/i18n/locale-context";
import { GlobalSourceSelector } from "@/components/shell/global-source-selector";
import { ConnectionsView } from "@/components/connections/connections-view";
import { getAppTranslations } from "@/lib/i18n/app-dictionary";
vi.mock("next/navigation", () => ({ usePathname: () => "/connections" }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); window.localStorage.clear(); });
it("keeps Connections and the global selection on the same server-confirmed dataset", async () => {
  let selected = "old";
  const sources = [
    { source_type: "dataset", source_id: "old", dataset_id: "old", display_name: "Old.xlsx", status: "ready", enabled: true },
    { source_type: "dataset", source_id: "new", dataset_id: "new", display_name: "Superstore.csv", status: "ready", enabled: true },
  ];
  const request = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.endsWith("/auth/me")) return Response.json({ user: { id: "u", permissions: ["data:read"] }, company: { id: "t", name: "Tenant" } });
    if (path.endsWith("/ai-credits")) return Response.json({});
    if (path.endsWith("/sources/active")) { selected = JSON.parse(String(init?.body)).source_id; return Response.json(sources.find(s => s.source_id === selected)); }
    if (path.endsWith("/sources/context")) return Response.json({ state: "READY", source_type: "dataset", source_id: selected, sources });
    if (path.endsWith("/sources")) return Response.json(sources.map(s => ({ ...s, active: s.source_id === selected })));
    return Response.json([]);
  });
  vi.stubGlobal("fetch", request);
  render(<LocaleProvider><SessionProvider><GlobalSourceSelector /><ConnectionsView /></SessionProvider></LocaleProvider>);
  await screen.findByRole("button", { name: /Source.*Old.xlsx/i });
  fireEvent.click(await screen.findByRole("button", { name: getAppTranslations("fr").integrations.selectSource }));
  await waitFor(() => expect(screen.getByRole("button", { name: /Source.*Superstore.csv/i })).toBeInTheDocument());
  expect(selected).toBe("new");
  expect(request.mock.calls.some(([url]) => String(url).endsWith("/enabled"))).toBe(false);
});
