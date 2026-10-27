import { NextRequest, NextResponse } from "next/server";
import { resolveAvenqoApiBase } from "@/lib/avenqo-api-base";

export const dynamic = "force-dynamic";

// The public OAuth callback stays on Railway. Complete the transaction on the
// initiating origin, where the browser's HttpOnly/Lax binding cookie exists.
// Authorization codes are single-use; never log them or follow upstream redirects.
export async function GET(request: NextRequest) {
  const destination = new URL("/crm?tab=connections", request.url);
  const binding = request.cookies.get("avenqo_oauth_bind")?.value;
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  let connected = false;
  if (binding && /^[a-f0-9]{64}$/.test(binding) && code && code.length < 4096 && state && state.length < 8192) {
    const upstream = new URL(`${resolveAvenqoApiBase()}/crm/calendar/google/callback`);
    upstream.searchParams.set("code", code);
    upstream.searchParams.set("state", state);
    try {
      const response = await fetch(upstream, {
        headers: { Cookie: `avenqo_oauth_bind=${binding}`, "X-Avenqo-Calendar-Relay": "1" },
        redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(45_000),
      });
      const location = response.headers.get("location");
      // No arbitrary redirects, backend cookies, JWTs or provider credentials
      // are propagated to the browser. The signed state is checked upstream.
      connected = response.status === 303 && !!location && new URL(location).origin === request.nextUrl.origin;
    } catch { /* Deliberately omit the request URL/code from diagnostics. */ }
  }
  destination.searchParams.set("calendar_oauth", connected ? "connected" : "failed");
  const result = NextResponse.redirect(destination, 303);
  result.headers.set("Cache-Control", "no-store");
  result.headers.set("Referrer-Policy", "no-referrer");
  result.cookies.set("avenqo_oauth_bind", "", { path: "/api/v1/crm/calendar", maxAge: 0, httpOnly: true, secure: true, sameSite: "lax" });
  return result;
}
