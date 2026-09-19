import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Routes qui nécessitent une authentification
const PROTECTED_ROUTES = [
  "/dashboard",
  "/crm",
  "/retail",
  "/data",
  "/integrations",
  "/billing",
  "/team",
  "/settings",
  "/admin",
  "/onboarding",
  "/assistant",
  "/agents",
  "/accounting",
  "/connections",
  "/support",
  "/marketing",
  "/voice",
  "/ocr",
  "/chatbots",
  "/automations",
];

// Routes publiques uniquement (redirect si déjà authentifié)
const AUTH_ONLY_ROUTES = ["/login", "/register", "/forgot-password", "/reset-password"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("avenqo_access_token")?.value;

  // Injecter le token dans les headers Authorization pour les API proxy
  const isApiRoute = pathname.startsWith("/api/v1/") || pathname.startsWith("/api/auth/");
  if (isApiRoute) {
    if (token && !request.headers.get("authorization")) {
      const requestHeaders = new Headers(request.headers);
      requestHeaders.set("authorization", `Bearer ${token}`);
      return NextResponse.next({ request: { headers: requestHeaders } });
    }
    return NextResponse.next();
  }

  // Protéger les routes authentifiées
  const isProtected = PROTECTED_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(route + "/")
  );

  if (isProtected && !token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Rediriger les utilisateurs authentifiés hors des pages auth
  const isAuthOnlyRoute = AUTH_ONLY_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(route + "/")
  );

  if (isAuthOnlyRoute && token) {
    const next = request.nextUrl.searchParams.get("next");
    const destination =
      next && PROTECTED_ROUTES.some((r) => next.startsWith(r)) ? next : "/dashboard";
    return NextResponse.redirect(new URL(destination, request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Routes à traiter (exclure assets statiques Next.js)
    "/((?!_next/static|_next/image|favicon.ico|brand/|public/).*)",
  ],
};
