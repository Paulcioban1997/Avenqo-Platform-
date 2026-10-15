/**
 * Lot 7 — k6 against authorized non-prod only.
 *
 * Refuses Production. Does not call paid OpenAI/Telnyx.
 * Numbers in Lot 8 are NOT TESTED until this script is actually run.
 *
 *   k6 run -e AVENQO_LOADTEST_BASE_URL=http://127.0.0.1:8000 loadtest/k6-mt-250.js
 */
import http from "k6/http";
import { check, fail } from "k6";

const FORBIDDEN = [
  "https://api.avenqo.ca",
  "https://avenqo.ca",
  "https://www.avenqo.ca",
];

export const options = {
  scenarios: {
    health_smoke: {
      executor: "constant-vus",
      vus: 1,
      duration: "10s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
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
  return raw;
}

export default function () {
  const base = origin();
  const res = http.get(`${base}/api/v1/health`);
  check(res, { "health is not 5xx": (r) => r.status < 500 });
}
