import { NextRequest } from "next/server";
import { afterEach, expect, it, vi } from "vitest";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules(); });

async function routes() {
  vi.stubEnv("VERCEL_ENV", "preview");
  vi.stubEnv("ENVIRONMENT", "production");
  vi.stubEnv("BACKEND_API_URL", "https://api.avenqo.ca");
  vi.resetModules();
  return import("@/app/api/auth/[action]/route");
}

it("sends login only to Sandbox and preserves a real credential rejection", async () => {
  const upstream = vi.fn().mockResolvedValue(Response.json({detail: "Invalid credentials"}, {status:401}));
  vi.stubGlobal("fetch", upstream);
  const {POST} = await routes();
  const response = await POST(new NextRequest("https://preview.invalid/api/auth/login", {
    method:"POST", body:JSON.stringify({email:"fixture@example.invalid", password:"fixture-only"}),
  }), {params:Promise.resolve({action:"login"})});
  expect(upstream.mock.calls[0][0]).toBe("https://avenqo-platform-sandbox.up.railway.app/api/v1/auth/login");
  expect(response.status).toBe(401);
  expect(response.headers.get("set-cookie")).toBeNull();
  expect(response.headers.get("x-avenqo-backend-origin")).toBe("https://avenqo-platform-sandbox.up.railway.app");
  expect(upstream.mock.calls[0][1].headers["X-Request-ID"]).toBe(response.headers.get("x-request-id"));
});

it("uses the same Sandbox upstream for authenticated me", async () => {
  const upstream = vi.fn().mockResolvedValue(Response.json({user:{id:"fixture-user"}}));
  vi.stubGlobal("fetch", upstream);
  const {GET} = await routes();
  const response = await GET(new NextRequest("https://preview.invalid/api/auth/me", {
    headers:{cookie:"avenqo_access_token=fixture-session"},
  }), {params:Promise.resolve({action:"me"})});
  expect(upstream.mock.calls[0][0]).toBe("https://avenqo-platform-sandbox.up.railway.app/api/v1/auth/me");
  expect(upstream.mock.calls[0][1].headers.Authorization).toBe("Bearer fixture-session");
  expect(response.status).toBe(200);
  expect(response.headers.get("x-avenqo-backend-origin")).toBe("https://avenqo-platform-sandbox.up.railway.app");
});
