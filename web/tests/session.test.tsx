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


function SourceSnapshot() {
  const { sourceContext, sourceSelectionState, sourceChoices, sourceRevision, activeDataSources, selectSource } = useSession();
  return <>
    <output>{sourceSelectionState ?? sourceContext?.source_id ?? "initial"}:{activeDataSources.join(",")}</output>
    <output data-testid="candidate-sources">{sourceChoices.map(source => source.source_id).join(",")}</output>
    <output data-testid="source-revision">{sourceRevision}</output>
    <button onClick={() => void selectSource("dataset", "A").catch(() => {})}>Keep A</button>
    <button onClick={() => void selectSource("dataset", "B").catch(() => {})}>Select B</button>
  </>;
}

function sourceFetch(onWrite: (id: string) => Promise<void>, failContext = () => false) {
  let selected = "A";
  const source = () => ({
    source_type: "dataset", source_id: selected, dataset_id: selected,
    display_name: `Dataset ${selected}`, enabled: true, status: "READY",
  });
  return vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/auth/me")) return Response.json({
      user: { id: "user-a", permissions: ["data:read"] },
      company: { id: "tenant-a", name: "Tenant A" },
    });
    if (url.endsWith("/ai-credits")) return Response.json({ monthly_remaining: 3 });
    if (url.endsWith("/active")) {
      const id = JSON.parse(String(options?.body)).source_id;
      await onWrite(id);
      selected = id;
      return Response.json({});
    }
    if (url.endsWith("/context")) return failContext()
      ? new Response(null, { status: 503 })
      : Response.json({ source_type: "dataset", source_id: selected, state: "READY", sources: [source()] });
    return Response.json([source()]);
  });
}

it("invalidates A immediately and serializes rapid A → B → A", async () => {
  let releaseB!: () => void;
  const blockedB = new Promise<void>(resolve => { releaseB = resolve; });
  const write = vi.fn(async (id: string) => { if (id === "B") await blockedB; });
  vi.stubGlobal("fetch", sourceFetch(write));
  render(<SessionProvider><SourceSnapshot /></SessionProvider>);
  await screen.findByText("A:Dataset A");
  act(() => screen.getByText("Select B").click());
  await waitFor(() => expect(write).toHaveBeenCalledWith("B"));
  expect(screen.getByText("pending:")).toBeInTheDocument();
  expect(screen.queryByText("A:Dataset A")).not.toBeInTheDocument();
  act(() => screen.getByText("Keep A").click());
  expect(write.mock.calls.map(([id]) => id)).toEqual(["B"]);
  await act(async () => { releaseB(); });
  await screen.findByText("A:Dataset A");
  expect(write.mock.calls.map(([id]) => id)).toEqual(["B", "A"]);
  expect(screen.getByTestId("source-revision")).toHaveTextContent("3");
  expect(screen.queryByText("B:Dataset B")).not.toBeInTheDocument();
});

it("keeps the snapshot invalid when PUT succeeds but context cannot be confirmed", async () => {
  let invalid = false;
  vi.stubGlobal("fetch", sourceFetch(async () => { invalid = true; }, () => invalid));
  render(<SessionProvider><SourceSnapshot /></SessionProvider>);
  await screen.findByText("A:Dataset A");
  act(() => screen.getByText("Select B").click());
  await screen.findByText("unconfirmed:");
  expect(screen.getByTestId("candidate-sources")).toHaveTextContent("A");
  expect(screen.queryByText(/Dataset [AB]/)).not.toBeInTheDocument();
});
