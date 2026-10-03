import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SessionProvider, useSession } from "@/lib/session-context";
import { apiFetch, ApiRequestError } from "@/lib/api-request";
import { CreditMeter } from "@/components/shell/credit-meter";

let route = "/dashboard";
vi.mock("next/navigation", () => ({ usePathname: () => route }));
vi.mock("next/link", () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); route = "/dashboard"; });

function Snapshot() {
  const { identity, credits, creditError, error } = useSession();
  return <div>{identity?.company.name}:{identity?.user.id}:{identity?.company.id}:{identity?.company.subscription_plan}:{credits.remaining}:{creditError?.category}:{error?.category}</div>;
}

it("keeps one backend identity and ledger throughout the exact navigation flow", async () => {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.endsWith("/auth/me")) return Response.json({ user: { id: "user-a" }, company: { id: "tenant-a", name: "Tenant A", subscription_plan: "base" }, organizations: [] });
    if (path.endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: 6227 });
    return Response.json([{ display_name: "Existing source", enabled: true }]);
  });
  vi.stubGlobal("fetch", fetch);
  const view = render(<SessionProvider><Snapshot /></SessionProvider>);
  await screen.findByText("Tenant A:user-a:tenant-a:base:6227::");
  for (const page of ["/retail", "/crm", "/retail", "/central-ai", "/connections", "/retail"]) {
    route = page;
    view.rerender(<SessionProvider><Snapshot key={page} /></SessionProvider>);
    expect(screen.getByText("Tenant A:user-a:tenant-a:base:6227::")).toBeInTheDocument();
  }
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/auth/me"))).toHaveLength(1);
  view.unmount();
  render(<SessionProvider><Snapshot /></SessionProvider>);
  await screen.findByText("Tenant A:user-a:tenant-a:base:6227::");
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/auth/me"))).toHaveLength(2);
});

it("shows an explicit credit failure and never turns a failed request into zero", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input) => String(input).endsWith("/auth/me")
    ? Response.json({ user: { id: "user-a" }, company: { id: "tenant-a", name: "Tenant A" } })
    : String(input).endsWith("/ai-credits") ? new Response(null, { status: 503 }) : Response.json([])));
  render(<SessionProvider><Snapshot /></SessionProvider>);
  await waitFor(() => expect(screen.getByText(/backend_error/)).toBeInTheDocument());
  expect(screen.queryByText(/:0:/)).not.toBeInTheDocument();
});

it("unknown credits never display zero percent", () => {
  render(<CreditMeter remaining={null} limit={null} label="Credits" upgradeLabel="Plan" error="Unavailable" />);
  expect(screen.queryByText("0%")).not.toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Unavailable");
});

it.each([[401, "session_expired"], [403, "unauthorized"], [402, "subscription_error"], [503, "backend_error"]])("classifies HTTP %i as %s", async (status, category) => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: Number(status) })));
  await expect(apiFetch("/api/v1/datasets")).rejects.toMatchObject({ category });
});

it("terminates a stalled request with an explicit timeout", async () => {
  const controller = new AbortController();
  vi.spyOn(AbortSignal, "timeout").mockReturnValue(controller.signal);
  vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(new DOMException("timeout", "TimeoutError"))))));
  const request = apiFetch("/api/v1/crm/appointments");
  controller.abort();
  await expect(request).rejects.toEqual(new ApiRequestError("timeout"));
});

it("revalidates a tenant change from another tab against the backend", async () => {
  const channels: Array<{ onmessage?: () => void }> = [];
  vi.stubGlobal("BroadcastChannel", class {
    onmessage?: () => void;
    constructor() { channels.push(this); }
    close() {}
  });
  let tenant = "a";
  vi.stubGlobal("fetch", vi.fn(async (input) => {
    if (String(input).endsWith("/auth/me")) return Response.json({ user: { id: "user-a" }, company: { id: tenant, name: `Tenant ${tenant}`, subscription_plan: "base" } });
    if (String(input).endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: tenant === "a" ? 6227 : 6000 });
    return Response.json([]);
  }));
  render(<SessionProvider><Snapshot /></SessionProvider>);
  await screen.findByText("Tenant a:user-a:a:base:6227::");
  tenant = "b";
  act(() => { channels[0].onmessage?.(); });
  await screen.findByText("Tenant b:user-a:b:base:6000::");
  expect(screen.queryByText(/Tenant a/)).not.toBeInTheDocument();
});

it("clears visible tenant and ledger when the backend expires the session", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input) => {
    if (String(input).endsWith("/auth/me")) return Response.json({ user: { id: "user-a" }, company: { id: "a", name: "Tenant A", subscription_plan: "base" } });
    if (String(input).endsWith("/ai-credits")) return Response.json({ monthly_included: 6500, monthly_remaining: 6227 });
    if (String(input).endsWith("/expired")) return new Response(null, { status: 401 });
    return Response.json([]);
  }));
  render(<SessionProvider><Snapshot /></SessionProvider>);
  await screen.findByText("Tenant A:user-a:a:base:6227::");
  await act(async () => { await expect(apiFetch("/api/v1/expired")).rejects.toMatchObject({ category: "session_expired" }); });
  expect(screen.getByText(/session_expired/)).toBeInTheDocument();
  expect(screen.queryByText(/Tenant A|6227|:0:/)).not.toBeInTheDocument();
});
