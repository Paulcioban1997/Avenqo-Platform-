import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const isStaging =
    process.env.ENVIRONMENT === "staging" ||
    process.env.NEXT_PUBLIC_ENVIRONMENT === "staging" ||
    process.env.VERCEL_ENV === "preview" ||
    process.env.VERCEL_ENV === "development";

  if (isStaging) {
    return {
      rules: [
        {
          userAgent: "*",
          disallow: ["/"],
        },
      ],
    };
  }

  const baseUrl = "https://avenqo.ca";

  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/pricing", "/terms", "/privacy"],
        disallow: [
          "/dashboard",
          "/dashboard/",
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
          "/admin",
          "/admin/",
          "/api",
          "/api/",
          "/login",
          "/register",
          "/app/",
          "/onboarding",
          "/assistant",
          "/connections",
          "/support",
          "/sales",
          "/customers",
          "/products",
          "/recommendations",
        ],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
    host: baseUrl,
  };
}
