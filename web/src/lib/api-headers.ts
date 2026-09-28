export function getAuthHeaders(): HeadersInit {
  // Authentication is carried by the canonical HttpOnly cookie and injected by
  // the Next.js proxy. Never let a stale localStorage token override it.
  return {};
}
