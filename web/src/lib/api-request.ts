import { getAuthHeaders } from "./api-headers";

export type ApiFailure = "session_expired" | "unauthorized" | "tenant_unresolved" | "subscription_error" | "backend_error" | "timeout";

export class ApiRequestError extends Error {
  constructor(public category: ApiFailure, public status?: number, public publicMessage?: string) {
    super(publicMessage ?? category);
  }
}

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(getAuthHeaders());
  new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  const deadline = AbortSignal.timeout(input.includes("/ai/") ? 100_000 : 30_000);
  try {
    const response = await fetch(input, {
      ...init, headers, credentials: "include", cache: "no-store",
      signal: init.signal ? AbortSignal.any([init.signal, deadline]) : deadline,
    });
    if (!response.ok) {
      const category: ApiFailure = response.status === 401 ? "session_expired"
        : response.status === 403 ? "unauthorized"
        : response.status === 402 ? "subscription_error"
        : "backend_error";
      if (response.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(new Event("avenqo:session-expired"));
      }
      const payload = await response.json().catch(() => null);
      let message: string | undefined = undefined;
      if (Array.isArray(payload?.error?.details) && payload.error.details.length > 0) {
        message = payload.error.details
          .map((item: any) => {
            const loc = Array.isArray(item.loc) ? item.loc.filter((p: any) => p !== "body").join(".") : "";
            return loc ? `${loc}: ${item.msg}` : item.msg;
          })
          .filter(Boolean)
          .join(" | ");
      } else if (typeof payload?.error?.message === "string") {
        message = payload.error.message;
      } else if (typeof payload?.detail === "string") {
        message = payload.detail;
      } else if (Array.isArray(payload?.detail)) {
        message = payload.detail
          .map((item: any) => {
            const loc = Array.isArray(item.loc) ? item.loc.filter((p: any) => p !== "body").join(".") : "";
            return loc ? `${loc}: ${item.msg}` : item.msg;
          })
          .filter(Boolean)
          .join(" | ");
      } else if (typeof payload?.message === "string") {
        message = payload.message;
      }
      throw new ApiRequestError(category, response.status, message);
    }
    return response;
  } catch (error) {
    if (error instanceof ApiRequestError) throw error;
    throw new ApiRequestError(deadline.aborted ? "timeout" : "backend_error");
  }
}
