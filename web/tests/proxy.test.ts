import { NextRequest } from "next/server";
import { afterEach, expect, it, vi } from "vitest";
import { proxy } from "@/proxy";

afterEach(() => { vi.unstubAllGlobals(); });

function token(exp: number) {
  return `header.${Buffer.from(JSON.stringify({ exp })).toString("base64url")}.signature`;
}

it("forwards the refreshed canonical cookie on the first API request", async () => {
  const fresh = token(Math.floor(Date.now() / 1000) + 1800);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ access_token: fresh, refresh_token: "rotated-refresh" })));
  const response = await proxy(new NextRequest("https://avenqo.ca/api/v1/auth/me", {
    headers: { cookie: `avenqo_access_token=${token(1)}; avenqo_refresh_token=existing-refresh; avenqo-locale=fr` },
  }));
  expect(response.headers.get("x-middleware-request-authorization")).toBe(`Bearer ${fresh}`);
  const cookies = response.headers.get("x-middleware-request-cookie");
  expect(cookies).toContain(`avenqo_access_token=${fresh}`);
  expect(cookies).toContain("avenqo_refresh_token=rotated-refresh");
  expect(cookies).toContain("avenqo-locale=fr");
  expect(cookies).not.toContain(token(1));
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
