/**
 * Multi-tenant palier harness. Isolated / non-prod only.
 *
 * Refuses Production. Default is a 1 VU health smoke.
 * Paliers 10→250 require AVENQO_LOADTEST_VUS and a loopback mock or explicit GO host.
 *
 *   k6 run -e AVENQO_LOADTEST_BASE_URL=http://127.0.0.1:18080 -e AVENQO_LOADTEST_VUS=10 loadtest/k6-mt-250.js
 */
import http from "k6/http";
import { check, fail } from "k6";

const FORBIDDEN = [
  "https://api.avenqo.ca",
  "https://avenqo.ca",
  "https://www.avenqo.ca",
];

const PALIERS = [10, 25, 50, 100, 150, 200, 250];
const vus = Number(__ENV.AVENQO_LOADTEST_VUS || 1);
const hold = __ENV.AVENQO_LOADTEST_HOLD || (vus === 1 ? "10s" : "20s");

if (vus !== 1 && !PALIERS.includes(vus)) {
  fail(`AVENQO_LOADTEST_VUS must be one of ${PALIERS.join(", ")} (or omit for smoke).`);
}

export const options = {
  scenarios: {
    palier: {
      executor: "constant-vus",
      vus,
      duration: hold,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<2000"],
  },
};

function origin() {
  const raw = (__ENV.AVENQO_LOADTEST_BASE_URL || "").replace(/\/$/, "");
  if (!raw) {
    fail("AVENQO_LOADTEST_BASE_URL is required. Production is forbidden.");
  }
  const normalized = raw.toLowerCase();
  if (FORBIDDEN.some((item) => normalized.startsWith(item))) {
    fail("Production origins are forbidden for Lot 7 load tests.");
  }
  if (vus >= 50 && !(normalized.startsWith("http://127.0.0.1") || normalized.startsWith("http://localhost"))) {
    fail("Paliers ≥50 must target loopback. Shared infrastructure is forbidden.");
  }
  return raw;
}

export default function () {
  const base = origin();
  const tenant = `company-${(__VU % vus) + 1}`;
  const headers = { "X-Simulated-Company-Id": tenant, "Content-Type": "application/json" };
  const health = http.get(`${base}/api/v1/health`, { headers });
  check(health, { "health is not 5xx": (r) => r.status < 500 });
  const login = http.post(`${base}/api/v1/auth/login`, JSON.stringify({ email: `${tenant}@loadtest.local` }), { headers });
  check(login, { "login is not 5xx": (r) => r.status < 500 });
  const chat = http.post(
    `${base}/api/v1/ai/chat`,
    JSON.stringify({ message: "ping simulated central" }),
    { headers },
  );
  check(chat, { "simulated AI is not 5xx": (r) => r.status < 500 });
}
