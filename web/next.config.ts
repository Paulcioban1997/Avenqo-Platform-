import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/dashboard",
        destination: "/app/index.html",
      },
      {
        source: "/retail",
        destination: "/app/index.html",
      },
      {
        source: "/retail/:path*",
        destination: "/app/index.html",
      },
      {
        source: "/central-ai",
        destination: "/app/index.html",
      },
      {
        source: "/data",
        destination: "/app/index.html",
      },
      {
        source: "/integrations",
        destination: "/app/index.html",
      },
      {
        source: "/billing",
        destination: "/app/index.html",
      },
      {
        source: "/team",
        destination: "/app/index.html",
      },
      {
        source: "/settings",
        destination: "/app/index.html",
      },
      {
        source: "/admin",
        destination: "/app/index.html",
      },
      {
        source: "/admin/:path*",
        destination: "/app/index.html",
      },
      {
        source: "/onboarding",
        destination: "/app/index.html",
      },
      {
        source: "/assistant",
        destination: "/app/index.html",
      },
      {
        source: "/agents",
        destination: "/app/index.html",
      },
      {
        source: "/connections",
        destination: "/app/index.html",
      },
      {
        source: "/support",
        destination: "/app/index.html",
      },
      // Legacy routes
      {
        source: "/sales",
        destination: "/app/index.html",
      },
      {
        source: "/customers",
        destination: "/app/index.html",
      },
      {
        source: "/products",
        destination: "/app/index.html",
      },
      {
        source: "/recommendations",
        destination: "/app/index.html",
      },
      // Flutter static assets
      {
        source: "/flutter_bootstrap.js",
        destination: "/app/flutter_bootstrap.js",
      },
      {
        source: "/main.dart.js",
        destination: "/app/main.dart.js",
      },
      {
        source: "/flutter.js",
        destination: "/app/flutter.js",
      },
      {
        source: "/flutter_service_worker.js",
        destination: "/app/flutter_service_worker.js",
      },
      {
        source: "/assets/:path*",
        destination: "/app/assets/:path*",
      },
      {
        source: "/canvaskit/:path*",
        destination: "/app/canvaskit/:path*",
      },
      {
        source: "/icons/:path*",
        destination: "/app/icons/:path*",
      },
      {
        source: "/version.json",
        destination: "/app/version.json",
      },
      {
        source: "/manifest.json",
        destination: "/app/manifest.json",
      },
      {
        source: "/favicon.png",
        destination: "/app/favicon.png",
      },
      // Backend FastAPI Gateway
      {
        source: "/api/v1/:path*",
        destination: `${process.env.BACKEND_API_URL || "http://127.0.0.1:8000"}/api/v1/:path*`,
      },
    ];
  },
  async redirects() {
    return [
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
        source: "/:path(dashboard|retail|central-ai|data|integrations|billing|team|settings|admin|app|api)/:subpath*",
        headers: [
          { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" },
        ],
      },
      {
        // Strictly prevent indexing of root private endpoints
        source: "/:path(dashboard|retail|central-ai|data|integrations|billing|team|settings|admin|onboarding|assistant|connections|support)",
        headers: [
          { key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" },
        ],
      },
    ];
  },
};

export default nextConfig;
