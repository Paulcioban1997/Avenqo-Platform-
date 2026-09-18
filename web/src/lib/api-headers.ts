export function getAuthHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("avenqo_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}
