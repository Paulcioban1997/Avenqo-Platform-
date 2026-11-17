import type { MetadataRoute } from "next";
import { isSandboxFrontend, resolvePublicSiteUrl } from "@/lib/public-site";

export default function robots(): MetadataRoute.Robots {
  if (isSandboxFrontend()) {
    return { rules: [{ userAgent: "*", disallow: "/" }] };
  }
  const baseUrl = resolvePublicSiteUrl();

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/dashboard",
          "/dashboard/",
          "/admin",
          "/admin/",
          "/api",
          "/api/",
          "/retail",
          "/retail/",
          "/central-ai",
          "/central-ai/",
          "/data",
          "/data/",
          "/integrations",
          "/integrations/",
          "/billing",
          "/billing/",
          "/team",
          "/team/",
          "/settings",
          "/settings/",
          "/connections",
          "/connections/",
          "/crm",
          "/crm/",
          "/accounting",
          "/accounting/",
          "/marketing",
          "/marketing/",
          "/automations",
          "/automations/",
          "/chatbots",
          "/chatbots/",
          "/voice",
          "/voice/",
          "/ocr",
          "/ocr/",
          "/agents",
          "/agents/",
          "/login",
          "/register",
          "/onboarding",
          "/assistant",
          "/support",
          "/forgot-password",
          "/reset-password",
          "/verify-email",
        ],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
    host: baseUrl,
  };
}
