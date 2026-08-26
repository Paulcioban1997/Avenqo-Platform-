import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = (
  process.env.AVENQO_API_BASE_URL ??
  process.env.AVENQO_API_URL ??
  process.env.API_BASE_URL ??
  "https://api.avenqo.ca/api/v1"
).replace(/\/$/, "");

const ALLOWED_ACTIONS = new Set(["login", "register"]);

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
    const upstream = await fetch(`${API_BASE_URL}/auth/${action}`, {
      method: "POST",
      headers: {
        "Content-Type": request.headers.get("content-type") ?? "application/json",
        Accept: "application/json",
      },
      body,
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
    console.error(`Avenqo auth proxy failed for ${action}`, error);
    return NextResponse.json(
      { detail: "Le service Avenqo est temporairement indisponible." },
      { status: 503 },
    );
  }
}

