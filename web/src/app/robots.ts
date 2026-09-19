import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const baseUrl = "https://avenqo.ca";

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
          "/reset-password",
          "/verify-email",
        ],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
    host: baseUrl,
  };
}
