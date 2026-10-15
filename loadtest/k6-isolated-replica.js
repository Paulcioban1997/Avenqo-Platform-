/**
 * Realistic palier against the isolated replica only (127.0.0.1).
 * Requires AVENQO_LOADTEST_EMAIL and AVENQO_LOADTEST_PASSWORD.
 */
import http from "k6/http";
import { check, fail } from "k6";

const vus = Number(__ENV.AVENQO_LOADTEST_VUS || 10);
const hold = __ENV.AVENQO_LOADTEST_HOLD || "15s";

export const options = {
  scenarios: { palier: { executor: "constant-vus", vus, duration: hold } },
  thresholds: { http_req_failed: ["rate<0.05"] },
};

function origin() {
  const raw = (__ENV.AVENQO_LOADTEST_BASE_URL || "").replace(/\/$/, "");
  if (!raw.startsWith("http://127.0.0.1") && !raw.startsWith("http://localhost")) {
    fail("Isolated k6 targets loopback only.");
  }
  return raw;
}

export default function () {
  const base = origin();
  const index = String((__VU % vus) + 1).padStart(3, "0");
  const prefix = __ENV.AVENQO_LOADTEST_EMAIL_PREFIX || "owner-iso-";
  const domain = __ENV.AVENQO_LOADTEST_EMAIL_DOMAIN || "example.com";
  const email = `${prefix}${index}@${domain}`;
  const login = http.post(
    `${base}/api/v1/auth/login`,
    JSON.stringify({ email, password: __ENV.AVENQO_LOADTEST_PASSWORD || "" }),
    { headers: { "Content-Type": "application/json" } },
  );
  check(login, { "login 200": (r) => r.status === 200 });
  const token = login.json("access_token");
  const headers = { Authorization: `Bearer ${token}` };
  check(http.get(`${base}/api/v1/auth/me`, { headers }), { "me": (r) => r.status === 200 });
  check(http.get(`${base}/api/v1/retail/status`, { headers }), { "retail": (r) => r.status < 500 });
  check(http.get(`${base}/api/v1/crm/clients`, { headers }), { "crm": (r) => r.status === 200 });
}
