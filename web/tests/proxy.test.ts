import { NextRequest } from "next/server";
import { afterEach, expect, it, vi } from "vitest";
import { proxy } from "@/proxy";

afterEach(() => { vi.unstubAllGlobals(); });

it.each(["/security", "/workspace/modules"])("protects %s before serving the page", async (path) => {
  const response = await proxy(new NextRequest(`https://avenqo.ca${path}`));
  expect(response.headers.get("location")).toContain("/login?next=");
});

function token(exp: number) {
  return `header.${Buffer.from(JSON.stringify({ exp })).toString("base64url")}.signature`;
}

it("does not rotate the refresh token on a rewritten API request", async () => {
  const current = token(1);
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  const response = await proxy(new NextRequest("https://avenqo.ca/api/v1/auth/me", {
    headers: { cookie: `avenqo_access_token=${current}; avenqo_refresh_token=existing-refresh; avenqo-locale=fr` },
  }));
  expect(fetchMock).not.toHaveBeenCalled();
  expect(response.headers.get("x-middleware-request-authorization")).toBe(`Bearer ${current}`);
  expect(response.headers.get("set-cookie")).toBeNull();
});

it("refreshes once on a page response that can store the new cookie", async () => {
  const fresh = token(Math.floor(Date.now() / 1000) + 1800);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ access_token: fresh, refresh_token: "rotated-refresh" })));
  const response = await proxy(new NextRequest("https://avenqo.ca/dashboard", {
    headers: { cookie: `avenqo_access_token=${token(1)}; avenqo_refresh_token=existing-refresh` },
  }));
  expect(response.headers.get("set-cookie")).toContain("avenqo_refresh_token=rotated-refresh");
  expect(response.headers.get("set-cookie")).toContain(`avenqo_access_token=${fresh}`);
});

it("reports refresh outage as 503 and preserves the existing session", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })));
  const response = await proxy(new NextRequest("https://avenqo.ca/retail", {
    headers: { cookie: `avenqo_access_token=${token(1)}; avenqo_refresh_token=existing-refresh` },
  }));
  expect(response.status).toBe(503);
  expect(response.headers.get("location")).toBeNull();
  expect(response.headers.get("set-cookie")).toBeNull();
});

it("allows the expired-session login page without redirecting on a revoked token", async () => {
  const response = await proxy(new NextRequest("https://avenqo.ca/login?session_expired=1", {
    headers: { cookie: `avenqo_access_token=${token(Math.floor(Date.now() / 1000) + 1800)}` },
  }));
  expect(response.headers.get("location")).toBeNull();
});
