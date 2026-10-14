import { expect, it } from "vitest";
import { resolveAvenqoApiBase, resolveAvenqoApiOrigin } from "@/lib/avenqo-api-base";

it("sends Vercel preview auth to Sandbox instead of localhost", () => {
  expect(
    resolveAvenqoApiOrigin({
      VERCEL_ENV: "preview",
      VERCEL_GIT_COMMIT_REF: "feat/sandbox-retail-reset-backup",
      AVENQO_API_BASE_URL: "http://127.0.0.1:8000",
    }),
  ).toBe("https://avenqo-platform-sandbox.up.railway.app");
  expect(
    resolveAvenqoApiBase({
      VERCEL_ENV: "preview",
      VERCEL_GIT_COMMIT_REF: "promotion/sandbox",
    }),
  ).toBe("https://avenqo-platform-sandbox.up.railway.app/api/v1");
});

it("keeps production Vercel on api.avenqo.ca", () => {
  expect(
    resolveAvenqoApiOrigin({
      VERCEL_ENV: "production",
      AVENQO_API_BASE_URL: "http://127.0.0.1:8000",
    }),
  ).toBe("https://api.avenqo.ca");
});

it("does not send preview traffic to production even if the env points there", () => {
  expect(
    resolveAvenqoApiOrigin({
      VERCEL_ENV: "preview",
      AVENQO_API_BASE_URL: "https://api.avenqo.ca",
    }),
  ).toBe("https://avenqo-platform-sandbox.up.railway.app");
});

it("uses localhost for local development", () => {
  expect(resolveAvenqoApiOrigin({})).toBe("http://127.0.0.1:8000");
});
