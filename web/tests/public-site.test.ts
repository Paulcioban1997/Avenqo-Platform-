import { expect, it } from "vitest";
import { isSandboxFrontend, resolvePublicSiteUrl } from "@/lib/public-site";

it("keeps the production site on avenqo.ca", () => {
  expect(isSandboxFrontend({})).toBe(false);
  expect(resolvePublicSiteUrl({})).toBe("https://avenqo.ca");
  expect(resolvePublicSiteUrl({ AVENQO_ENVIRONMENT: "production" })).toBe("https://avenqo.ca");
});

it("does not canonicalise a sandbox frontend to avenqo.ca", () => {
  expect(resolvePublicSiteUrl({
    AVENQO_ENVIRONMENT: "sandbox",
    RENDER_EXTERNAL_URL: "https://avenqo-sandbox.onrender.com",
  })).toBe("https://avenqo-sandbox.onrender.com");
  expect(resolvePublicSiteUrl({
    AVENQO_ENVIRONMENT: "sandbox",
    AVENQO_PUBLIC_URL: "https://avenqo.ca",
  })).toBe("http://127.0.0.1:3000");
  expect(resolvePublicSiteUrl({
    AVENQO_ENVIRONMENT: "sandbox",
    RENDER_EXTERNAL_URL: "https://api.avenqo.ca",
  })).toBe("http://127.0.0.1:3000");
});
