import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const rawApiBase = (
  process.env.AVENQO_API_BASE_URL ??
  process.env.AVENQO_API_URL ??
  process.env.API_BASE_URL ??
  process.env.BACKEND_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");
const API_BASE_URL = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

function tokenExpiresSoon(token: string): boolean {
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8"));
    return typeof payload.exp !== "number" || payload.exp <= Math.floor(Date.now() / 1000) + 30;
  } catch {
    return true;
  }
}

async function refreshAccessToken(refreshToken: string): Promise<{ accessToken: string; refreshToken?: string } | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "avenqo-web" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
    if (!response.ok) return null;
    const payload = await response.json();
    return payload.access_token
      ? { accessToken: payload.access_token, refreshToken: payload.refresh_token }
      : null;
  } catch {
    return null;
  }
}

function setAuthCookies(response: NextResponse, tokens: { accessToken: string; refreshToken?: string }): void {
  response.cookies.set("avenqo_access_token", tokens.accessToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 30 * 60,
  });
  if (tokens.refreshToken) {
    response.cookies.set("avenqo_refresh_token", tokens.refreshToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 30 * 86400,
    });
  }
}

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

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  let token = request.cookies.get("avenqo_access_token")?.value;
  const refreshToken = request.cookies.get("avenqo_refresh_token")?.value;

  let refreshedTokens: { accessToken: string; refreshToken?: string } | null = null;
  if ((!token || tokenExpiresSoon(token)) && refreshToken && pathname !== "/api/auth/refresh") {
    refreshedTokens = await refreshAccessToken(refreshToken);
    token = refreshedTokens?.accessToken;
  }

  // Injecter le token dans les headers Authorization pour les API proxy
  const isApiRoute = pathname.startsWith("/api/v1/") || pathname.startsWith("/api/auth/");
  if (isApiRoute) {
    const requestHeaders = new Headers(request.headers);
    const locale = request.cookies.get("avenqo-locale")?.value;
    if (locale) requestHeaders.set("Accept-Language", locale);
    if (token) {
      requestHeaders.set("authorization", `Bearer ${token}`);
    }
    const response = NextResponse.next({ request: { headers: requestHeaders } });
    if (refreshedTokens) setAuthCookies(response, refreshedTokens);
    return response;
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

  const response = NextResponse.next();
  if (refreshedTokens) setAuthCookies(response, refreshedTokens);
  return response;
}

export const config = {
  matcher: [
    // Routes à traiter (exclure assets statiques Next.js)
    "/((?!_next/static|_next/image|favicon.ico|brand/|public/).*)",
  ],
};
