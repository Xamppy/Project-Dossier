/**
 * Saturación dossier — escenarios C (dedup async) y E (créditos límite).
 *
 * Requisitos:
 *   - API en BASE_URL (default http://127.0.0.1:8000)
 *   - k6 instalado: https://k6.io/docs/get-started/installation/
 *   - Token JWT de un usuario mutator (admin/user) en K6_AUTH_TOKEN
 *   - Org con créditos conocidos para escenario E (K6_EXPECT_CREDITS=1)
 *
 * Uso:
 *   k6 run scripts/load/k6-dossier-saturation.js
 *   k6 run -e K6_SCENARIO=dedup scripts/load/k6-dossier-saturation.js
 *   k6 run -e K6_SCENARIO=credits scripts/load/k6-dossier-saturation.js
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";
const AUTH_TOKEN = __ENV.K6_AUTH_TOKEN || "";
const SCENARIO = (__ENV.K6_SCENARIO || "both").toLowerCase();

const dedupJobsCreated = new Counter("dedup_jobs_created");
const dedupDuplicateResponses = new Counter("dedup_same_job_id");
const credits402 = new Counter("credits_insufficient_402");
const personLatency = new Trend("person_research_latency_ms");

function authHeaders() {
  return {
    Authorization: `Bearer ${AUTH_TOKEN}`,
    "Content-Type": "application/json",
  };
}

function postPersonAsync(uniqueSuffix) {
  const payload = JSON.stringify({
    full_name: `K6 Load Test ${uniqueSuffix}`,
    company: "Saturation Corp",
    email: `k6-${uniqueSuffix}@example.com`,
    async_mode: true,
    research_source: "pdl",
  });
  const res = http.post(`${BASE_URL}/dossiers/person/research`, payload, {
    headers: authHeaders(),
    tags: { name: "person_async" },
  });
  personLatency.add(res.timings.duration);
  return res;
}

/** Escenario C: 10 VUs disparan el mismo nombre a la vez → esperar 1 job_id. */
export function scenarioDedup() {
  if (!AUTH_TOKEN) {
    console.error("K6_AUTH_TOKEN requerido");
    return;
  }
  const suffix = __ENV.K6_DEDUP_SUFFIX || "dedup-fixed-name";
  const res = postPersonAsync(suffix);
  check(res, {
    "dedup status 200 or 402": (r) => r.status === 200 || r.status === 402,
  });
  if (res.status === 200) {
    try {
      const body = res.json();
      if (body.job_id) {
        dedupJobsCreated.add(1);
        const jobId = body.job_id;
        const list = http.get(
          `${BASE_URL}/dossier-generation-jobs?active_only=true&limit=10`,
          { headers: authHeaders() }
        );
        if (list.status === 200) {
          const jobs = list.json("jobs") || [];
          const same = jobs.filter((j) => j.id === jobId).length;
          if (same >= 1) dedupDuplicateResponses.add(1);
        }
      }
    } catch (_) {
      /* ignore parse */
    }
  }
  sleep(0.5);
}

/** Escenario E: org con 1 crédito — segunda generación sync debería 402. */
export function scenarioCredits() {
  if (!AUTH_TOKEN) {
    console.error("K6_AUTH_TOKEN requerido");
    return;
  }
  const suffix = `credit-${__VU}-${__ITER}-${Date.now()}`;
  const payload = JSON.stringify({
    full_name: `K6 Credit Test ${suffix}`,
    async_mode: false,
    research_source: "pdl",
  });
  const res = http.post(`${BASE_URL}/dossiers/person/research`, payload, {
    headers: authHeaders(),
    timeout: "120s",
    tags: { name: "person_sync" },
  });
  if (res.status === 402) {
    credits402.add(1);
  }
  check(res, {
    "credit test not 500": (r) => r.status !== 500,
  });
  sleep(1);
}

export const options = {
  scenarios: buildScenarios(),
  thresholds: {
    http_req_failed: ["rate<0.5"],
  },
};

function buildScenarios() {
  const out = {};
  if (SCENARIO === "dedup" || SCENARIO === "both") {
    out.dedup_burst = {
      executor: "shared-iterations",
      exec: "scenarioDedup",
      vus: 10,
      iterations: 10,
      maxDuration: "2m",
    };
  }
  if (SCENARIO === "credits" || SCENARIO === "both") {
    out.credits_limit = {
      executor: "per-vu-iterations",
      exec: "scenarioCredits",
      vus: 3,
      iterations: 2,
      maxDuration: "5m",
      startTime: SCENARIO === "both" ? "30s" : "0s",
    };
  }
  return out;
}

export default function () {
  scenarioDedup();
}
