// k6 Load Testing Script for AgentHub
// Run with: k6 run perf/load_test.js

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// Custom metrics
const errorRate = new Rate("errors");
const sessionCreationTime = new Trend("session_creation_time");
const planCreationTime = new Trend("plan_creation_time");
const executionTime = new Trend("execution_time");

// Configuration
const BASE_URL = __ENV.API_URL || "http://localhost:8080";
const API_KEY = __ENV.API_KEY || "test_api_key";

// Test scenarios
export const options = {
  scenarios: {
    // Scenario 1: Non-LLM routes (p95 < 300ms target)
    non_llm_routes: {
      executor: "constant-vus",
      vus: 10,
      duration: "1m",
      exec: "testNonLLMRoutes",
      tags: { scenario: "non_llm" },
    },

    // Scenario 2: Single-tool plans (p95 < 2.5s target)
    single_tool_plans: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "30s", target: 5 },
        { duration: "1m", target: 5 },
        { duration: "30s", target: 0 },
      ],
      exec: "testSingleToolPlan",
      tags: { scenario: "single_tool" },
      startTime: "1m30s",
    },

    // Scenario 3: Burst test for rate limiter
    burst_test: {
      executor: "constant-arrival-rate",
      rate: 20, // 20 requests per second
      timeUnit: "1s",
      duration: "30s",
      preAllocatedVUs: 5,
      maxVUs: 20,
      exec: "testBurst",
      tags: { scenario: "burst" },
      startTime: "3m",
    },
  },

  thresholds: {
    // Non-LLM routes should be fast
    "http_req_duration{scenario:non_llm}": ["p(95)<300"],

    // Single-tool plans can be slower but should meet SLO
    "http_req_duration{scenario:single_tool}": ["p(95)<2500"],

    // Overall error rate should be low
    errors: ["rate<0.1"], // Less than 10% errors

    // Rate limit blocks are expected in burst test
    "http_req_failed{scenario:burst}": ["rate<0.3"], // Allow up to 30% rate limiting
  },
};

// Helper function to make authenticated requests
function makeRequest(method, path, body = null) {
  const headers = {
    Authorization: `Bearer ${API_KEY}`,
    "Content-Type": "application/json",
  };

  const url = `${BASE_URL}${path}`;

  let response;
  if (method === "GET") {
    response = http.get(url, { headers });
  } else if (method === "POST") {
    response = http.post(url, JSON.stringify(body), { headers });
  }

  return response;
}

// Scenario 1: Test non-LLM routes
export function testNonLLMRoutes() {
  group("Non-LLM Routes", function () {
    // Health check
    let response = http.get(`${BASE_URL}/healthz`);
    check(response, {
      "health check status is 200": (r) => r.status === 200,
      "health check response time < 50ms": (r) => r.timings.duration < 50,
    });
    errorRate.add(response.status !== 200);

    sleep(0.1);

    // List tools
    response = makeRequest("GET", "/v1/tools");
    check(response, {
      "list tools status is 200": (r) => r.status === 200,
      "list tools response time < 100ms": (r) => r.timings.duration < 100,
      "tools list is not empty": (r) => {
        try {
          return JSON.parse(r.body).length > 0;
        } catch {
          return false;
        }
      },
    });
    errorRate.add(response.status !== 200);

    sleep(0.1);

    // Create session
    response = makeRequest("POST", "/v1/sessions", {});
    sessionCreationTime.add(response.timings.duration);
    check(response, {
      "create session status is 200 or 201": (r) =>
        r.status === 200 || r.status === 201,
      "create session response time < 200ms": (r) => r.timings.duration < 200,
      "session has ID": (r) => {
        try {
          return JSON.parse(r.body).session_id !== undefined;
        } catch {
          return false;
        }
      },
    });
    errorRate.add(response.status !== 200 && response.status !== 201);

    // Get session (if created successfully)
    if (response.status === 200 || response.status === 201) {
      try {
        const sessionId = JSON.parse(response.body).session_id;
        const getResponse = makeRequest("GET", `/v1/sessions/${sessionId}`);
        check(getResponse, {
          "get session status is 200": (r) => r.status === 200,
          "get session response time < 50ms": (r) => r.timings.duration < 50,
        });
        errorRate.add(getResponse.status !== 200);
      } catch (e) {
        // Handle parsing errors
      }
    }
  });

  sleep(1);
}

// Scenario 2: Test single-tool plan and execution
export function testSingleToolPlan() {
  group("Single-Tool Plan", function () {
    // Create session
    let response = makeRequest("POST", "/v1/sessions", {});

    if (response.status !== 200 && response.status !== 201) {
      errorRate.add(true);
      return;
    }

    let sessionId;
    try {
      sessionId = JSON.parse(response.body).session_id;
    } catch {
      errorRate.add(true);
      return;
    }

    sleep(0.5);

    // Execute a simple plan (mock execution without actual LLM)
    const plan = {
      steps: [
        {
          tool: "search",
          args: { query: "test query" },
          step_id: "step_0",
        },
      ],
      rationale: "Test plan for load testing",
      created_at: new Date().toISOString(),
      estimated_tokens: 100,
    };

    response = makeRequest("POST", "/v1/execute", {
      session_id: sessionId,
      plan: plan,
    });

    executionTime.add(response.timings.duration);

    check(response, {
      "execute status is 200": (r) => r.status === 200,
      "execute response time < 2500ms": (r) => r.timings.duration < 2500,
      "execution has results": (r) => {
        try {
          return JSON.parse(r.body).steps !== undefined;
        } catch {
          return false;
        }
      },
    });
    errorRate.add(response.status !== 200);
  });

  sleep(1);
}

// Scenario 3: Burst test for rate limiter
export function testBurst() {
  const response = makeRequest("POST", "/v1/sessions", {});

  check(response, {
    "burst request completed": (r) =>
      r.status === 200 || r.status === 201 || r.status === 429,
    "rate limit headers present on 429": (r) => {
      if (r.status === 429) {
        return r.headers["X-Ratelimit-Limit"] !== undefined;
      }
      return true;
    },
  });

  // Don't count 429 as error in burst test - it's expected
  errorRate.add(
    response.status !== 200 &&
      response.status !== 201 &&
      response.status !== 429
  );
}

// Setup and teardown
export function setup() {
  console.log(`Starting load test against ${BASE_URL}`);

  // Verify API is accessible
  const response = http.get(`${BASE_URL}/healthz`);
  if (response.status !== 200) {
    console.error("API is not healthy. Aborting test.");
    return { abort: true };
  }

  return { abort: false };
}

export function teardown(data) {
  if (data.abort) {
    console.log("Test was aborted due to setup failure");
    return;
  }

  console.log("Load test completed");
}
