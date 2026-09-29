import { DEFAULT_LOCALE } from "@/lib/i18n/locales";

export function getAuthHeaders(): HeadersInit {
  // Authentication is carried by the canonical HttpOnly cookie and injected by
  // the Next.js proxy. Never let a stale localStorage token override it.
  if (typeof window === "undefined") return {};
  try {
    return {
      "Accept-Language": window.localStorage.getItem("avenqo-locale") || DEFAULT_LOCALE,
    };
  } catch {
    return { "Accept-Language": DEFAULT_LOCALE };
  }
}
