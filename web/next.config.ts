import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // Backend FastAPI Gateway — seul rewrite conservé
      // Toutes les routes SaaS sont servies nativement par Next.js App Router
      {
        source: "/api/v1/:path*",
        destination: `${process.env.BACKEND_API_URL || "http://127.0.0.1:8000"}/api/v1/:path*`,
      },
    ];
  },
  async redirects() {
    return [
      // Redirect permanent : app.avenqo.ca → avenqo.ca (conservation du path + query params)
      {
        source: "/:path*",
        has: [{ type: "host", value: "app.avenqo.ca" }],
        destination: "https://avenqo.ca/:path*",
        permanent: true,
      },
      // Redirect permanent : www.avenqo.ca → avenqo.ca
      {
        source: "/:path*",
        has: [{ type: "host", value: "www.avenqo.ca" }],
        destination: "https://avenqo.ca/:path*",
        permanent: true,
      },
    ];
  },
  async headers() {
    const isStaging =
      process.env.ENVIRONMENT === "staging" ||
      process.env.NEXT_PUBLIC_ENVIRONMENT === "staging" ||
      process.env.VERCEL_ENV === "preview" ||
      process.env.VERCEL_ENV === "development";

    const globalHeaders = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "SAMEORIGIN" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    ];

    if (isStaging) {
      globalHeaders.push({
        key: "X-Robots-Tag",
        value: "noindex, nofollow, noarchive",
      });
    }

    return [
      {
        // Global basic security headers for all routes
        source: "/:path*",
        headers: globalHeaders,
      },
      {
        // Strictly prevent indexing of private SaaS and app routes via HTTP headers
        source: "/:path(dashboard|retail|central-ai|data|integrations|billing|team|settings|admin|crm|api)/:subpath*",
        headers: [
          { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" },
        ],
      },
      {
        // Strictly prevent indexing of root private endpoints
        source: "/:path(dashboard|retail|central-ai|data|integrations|billing|team|settings|admin|onboarding|assistant|connections|support|crm|accounting)",
        headers: [
          { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" },
        ],
      },
    ];
  },
};

export default nextConfig;
