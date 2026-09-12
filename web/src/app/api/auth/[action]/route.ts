import { NextRequest, NextResponse } from "next/server";

const rawBase = (
  process.env.AVENQO_API_BASE_URL ??
  process.env.AVENQO_API_URL ??
  process.env.API_BASE_URL ??
  process.env.BACKEND_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const API_BASE_URL = rawBase.endsWith("/api/v1") ? rawBase : `${rawBase}/api/v1`;

const ALLOWED_ACTIONS = new Set(["login", "register", "refresh", "logout", "me"]);

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ action: string }> },
) {
  const { action } = await context.params;

  if (!ALLOWED_ACTIONS.has(action)) {
    return NextResponse.json({ detail: "Auth action not found." }, { status: 404 });
  }

  try {
    const body = await request.text();
    const headers: Record<string, string> = {
      "Content-Type": request.headers.get("content-type") ?? "application/json",
      Accept: "application/json",
    };
    const incomingCookie = request.headers.get("cookie");
    if (incomingCookie) headers["Cookie"] = incomingCookie;
    const secFetchSite = request.headers.get("sec-fetch-site");
    if (secFetchSite) headers["Sec-Fetch-Site"] = secFetchSite;
    const csrfToken = request.headers.get("x-csrf-token");
    if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
    const xRequestedWith = request.headers.get("x-requested-with");
    const token = request.cookies.get("avenqo_access_token")?.value;
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const upstream = await fetch(`${API_BASE_URL}/auth/${action}`, {
      method: "POST",
      headers,
      body: body || undefined,
      cache: "no-store",
    });

    const responseBody = await upstream.text();
    const responseHeaders = new Headers();
    responseHeaders.set("Content-Type", upstream.headers.get("content-type") ?? "application/json");

    const response = new NextResponse(responseBody, {
      status: upstream.status,
      headers: responseHeaders,
    });

    // Relayer tous les Set-Cookie de FastAPI vers le navigateur
    const setCookies = upstream.headers.getSetCookie
      ? upstream.headers.getSetCookie()
      : [upstream.headers.get("set-cookie")].filter(Boolean) as string[];

    for (const cookie of setCookies) {
      response.headers.append("set-cookie", cookie);
    }

    // Défense en profondeur : si FastAPI a renvoyé les tokens en JSON, définir directement les cookies HttpOnly sur NextResponse
    const isSecure = process.env.NODE_ENV === "production" || process.env.ENVIRONMENT === "staging" || process.env.VERCEL_ENV !== "development";
    if (upstream.status === 200 && (action === "login" || action === "refresh")) {
      try {
        const parsed = JSON.parse(responseBody);
        if (parsed.access_token) {
          response.cookies.set({
            name: "avenqo_access_token",
            value: parsed.access_token,
            httpOnly: true,
            secure: isSecure,
            sameSite: "lax",
            path: "/",
            maxAge: 30 * 60,
          });
        }
        if (parsed.refresh_token) {
          response.cookies.set({
            name: "avenqo_refresh_token",
            value: parsed.refresh_token,
            httpOnly: true,
            secure: isSecure,
            sameSite: "lax",
            path: "/",
            maxAge: 30 * 86400,
          });
        }
        const csrfVal = parsed.csrf_token || (Math.random().toString(36).substring(2) + Date.now().toString(36));
        response.cookies.set({
          name: "avenqo_csrf",
          value: csrfVal,
          httpOnly: false,
          secure: isSecure,
          sameSite: "lax",
          path: "/",
          maxAge: 30 * 86400,
        });
      } catch {
        // Ignorer erreur parse JSON
      }
    } else if (action === "logout") {
      response.cookies.delete("avenqo_access_token");
      response.cookies.delete("avenqo_refresh_token");
      response.cookies.delete("avenqo_csrf");
    }

    return response;
  } catch (error) {
    console.error(`Avenqo auth proxy failed for ${action}`, error);
    return NextResponse.json(
      { detail: "Le service Avenqo est temporairement indisponible." },
      { status: 503 },
    );
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ action: string }> },
) {
  const { action } = await context.params;

  if (action !== "me") {
    return NextResponse.json({ detail: "Auth action not found." }, { status: 404 });
  }

  try {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    const incomingCookie = request.headers.get("cookie");
    if (incomingCookie) headers["Cookie"] = incomingCookie;
    const authHeader = request.headers.get("authorization");
    if (authHeader) headers["Authorization"] = authHeader;
    const token = request.cookies.get("avenqo_access_token")?.value;
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const upstream = await fetch(`${API_BASE_URL}/auth/me`, {
      method: "GET",
      headers,
      cache: "no-store",
    });

    const responseBody = await upstream.text();
    return new NextResponse(responseBody, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    console.error("Avenqo auth proxy failed for me", error);
    return NextResponse.json(
      { detail: "Le service Avenqo est temporairement indisponible." },
      { status: 503 },
    );
  }
}

