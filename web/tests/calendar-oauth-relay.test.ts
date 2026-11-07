import { NextRequest } from "next/server";
import { afterEach, expect, it, vi } from "vitest";
import { GET } from "@/app/api/v1/crm/calendar/google/relay/route";
const origin = "https://preview.example.test";
const binding = "a".repeat(64);
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
it("fails closed without the original browser binding and never calls the API", async () => {
  const upstream = vi.fn(); vi.stubGlobal("fetch", upstream);
  const response = await GET(new NextRequest(`${origin}/api/v1/crm/calendar/google/relay?code=fixture-code&state=fixture-state`));
  expect(upstream).not.toHaveBeenCalled();
  expect(response.headers.get("location")).toBe(`${origin}/crm?tab=connections&calendar_oauth=failed`);
});
it("forwards only the binding to Sandbox and discards provider secrets", async () => {
  vi.stubEnv("VERCEL_ENV", "preview");
  const upstream = vi.fn().mockResolvedValue(new Response(null, { status:303, headers:{location:`${origin}/crm?tab=connections`, "set-cookie":"must-not-leak=fixture"} }));
  vi.stubGlobal("fetch", upstream);
  const response = await GET(new NextRequest(`${origin}/api/v1/crm/calendar/google/relay?code=fixture-code&state=fixture-state`, { headers:{cookie:`avenqo_oauth_bind=${binding}; avenqo_access_token=fixture-session`} }));
  expect(String(upstream.mock.calls[0][0])).toContain("https://avenqo-platform-sandbox.up.railway.app/api/v1/crm/calendar/google/callback?");
  expect(upstream.mock.calls[0][1].headers.Cookie).toBe(`avenqo_oauth_bind=${binding}`);
  expect(upstream.mock.calls[0][1].redirect).toBe("manual");
  expect(response.headers.get("location")).toBe(`${origin}/crm?tab=connections&calendar_oauth=connected`);
  expect(response.headers.get("set-cookie")).not.toContain("must-not-leak");
  expect(response.headers.get("referrer-policy")).toBe("no-referrer");
});
it("rejects an upstream redirect to a different tenant frontend", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, {status:303, headers:{location:"https://untrusted.example/crm"}})));
  const response = await GET(new NextRequest(`${origin}/api/v1/crm/calendar/google/relay?code=fixture-code&state=fixture-state`, {headers:{cookie:`avenqo_oauth_bind=${binding}`}}));
  expect(response.headers.get("location")).toContain("calendar_oauth=failed");
});
