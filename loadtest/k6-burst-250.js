/**
 * One-shot 250 simultaneous HTTP requests against the isolated replica only.
 */
import http from "k6/http";
import { check, fail } from "k6";

const vus = Number(__ENV.AVENQO_LOADTEST_VUS || 250);

export const options = {
  scenarios: {
    burst: {
      executor: "per-vu-iterations",
      vus,
      iterations: 1,
      maxDuration: "90s",
    },
  },
  thresholds: { http_req_failed: ["rate<0.05"] },
};

export function setup() {
  const base = (__ENV.AVENQO_LOADTEST_BASE_URL || "").replace(/\/$/, "");
  if (!base.startsWith("http://127.0.0.1") && !base.startsWith("http://localhost")) {
    fail("Burst k6 targets loopback only.");
  }
  const prefix = __ENV.AVENQO_LOADTEST_EMAIL_PREFIX || "owner-iso-";
  const domain = __ENV.AVENQO_LOADTEST_EMAIL_DOMAIN || "example.com";
  const password = __ENV.AVENQO_LOADTEST_PASSWORD || "";
  const tokens = [];
  for (let i = 1; i <= vus; i += 1) {
    const email = `${prefix}${String(i).padStart(3, "0")}@${domain}`;
    const login = http.post(
      `${base}/api/v1/auth/login`,
      JSON.stringify({ email, password }),
      { headers: { "Content-Type": "application/json" } },
    );
    tokens.push(login.json("access_token") || "");
  }
  return { base, tokens };
}

export default function (data) {
  const token = data.tokens[__VU - 1];
  const headers = { Authorization: `Bearer ${token}` };
  const me = http.get(`${data.base}/api/v1/auth/me`, { headers });
  check(me, { "me 200": (r) => r.status === 200 });
}
