export function getAuthHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("avenqo_token") || localStorage.getItem("avenqo_access_token");
  const headers: Record<string, string> = {
    "X-Company-ID": "9c97cb94-e9f9-46fb-afd4-8a1d21019cff",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}
