// k6 load test for the two busiest days: results release (parents open report cards)
// and the fee deadline (parents check what they owe).
//
//   k6 run -e BASE=https://api.staging.nexedu.com.gh -e SCHOOL=greenfield \
//          -e EMAIL=parent@greenfield.test -e PASSWORD=... loadtest/results-and-fees.js
//
// Run against staging only, never production. Targets (Phase 9): p95 under 800 ms for
// reads, under 1% errors, at 300 parents a minute per school across 20 schools.
import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE || "http://127.0.0.1:8000";
const SCHOOL = __ENV.SCHOOL || "greenfield";

export const options = {
  scenarios: {
    results_day: {
      executor: "ramping-arrival-rate",
      exec: "resultsDay",
      startRate: 5,
      timeUnit: "1s",
      preAllocatedVUs: 50,
      maxVUs: 400,
      stages: [
        { target: 50, duration: "2m" },
        { target: 100, duration: "5m" },
        { target: 0, duration: "1m" },
      ],
    },
    fee_deadline: {
      executor: "constant-arrival-rate",
      exec: "feeDeadline",
      rate: 30,
      timeUnit: "1s",
      duration: "8m",
      preAllocatedVUs: 30,
      maxVUs: 200,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{kind:read}": ["p(95)<800"],
  },
};

export function setup() {
  const login = http.post(
    `${BASE}/_allauth/app/v1/auth/login`,
    JSON.stringify({ email: __ENV.EMAIL, password: __ENV.PASSWORD }),
    { headers: { "Content-Type": "application/json" } },
  );
  check(login, { "signed in": (r) => r.status === 200 });
  return { token: login.json("meta.access_token") };
}

function headers(data) {
  return { headers: { Authorization: `Bearer ${data.token}`, "X-Tenant": SCHOOL }, tags: { kind: "read" } };
}

export function resultsDay(data) {
  const cards = http.get(`${BASE}/api/v1/assessments/report-cards/`, headers(data));
  check(cards, { "report cards": (r) => r.status === 200 });
  http.get(`${BASE}/api/v1/communication/notifications/unread_count/`, headers(data));
  sleep(1);
}

export function feeDeadline(data) {
  const invoices = http.get(`${BASE}/api/v1/finance/invoices/`, headers(data));
  check(invoices, { invoices: (r) => r.status === 200 });
  http.get(`${BASE}/api/v1/me/`, headers(data));
  sleep(1);
}
