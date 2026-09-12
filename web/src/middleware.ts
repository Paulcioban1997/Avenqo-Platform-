import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("avenqo_access_token")?.value;
  if (token && !request.headers.get("authorization")) {
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set("authorization", `Bearer ${token}`);
    return NextResponse.next({
      request: {
        headers: requestHeaders,
      },
    });
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/api/v1/:path*", "/api/auth/:path*"],
};
