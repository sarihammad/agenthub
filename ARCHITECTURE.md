# AgentHub Architecture

## Overview

AgentHub is a production-ready agentic orchestrator that combines planning, execution, governance, and observability into a cohesive system. This document describes the architecture, data flows, design decisions, and tradeoffs.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Client                                 │
└──────────────┬──────────────────────────────────────────────────┘
               │ HTTP/SSE
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       FastAPI Gateway                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Middleware: Auth | Rate Limit | Metrics | Audit         │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬───────────────────┬──────────────────────┬───────────────┘
       │                   │                      │
       ▼                   ▼                      ▼
┌──────────────┐    ┌──────────────┐      ┌──────────────┐
│   Planner    │    │   Executor   │      │   Session    │
│              │    │              │      │    Store     │
│  - LLM       │    │  - Tools     │      │              │
│  - Function  │    │  - Retries   │      │  (Redis)     │
│    Calling   │    │  - Caching   │      │              │
└──────┬───────┘    └──────┬───────┘      └──────────────┘
       │                   │
       └───────┬───────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Tool Registry                              │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  search  │  │http_fetch│  │retrieve_ │  │ads_metrics_  │  │
│  │          │  │          │  │   doc    │  │    mock      │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Observability Stack                          │
│                                                                 │
│  OpenTelemetry ────▶ OTLP Collector ────▶ Prometheus          │
│                                           Grafana               │
│  Structured Logs ───▶ JSON ──────────▶ (stdout)                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      Kafka (Redpanda)                           │
│                                                                 │
│  Topics: audit.logs, agent.events, dead.letter                 │
│                                                                 │
│  Consumers: AuditConsumer, DLQConsumer                          │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Planner

**Responsibility**: Convert goals into executable plans using LLM function calling.

**Flow**:

1. Receives goal + context + allowed tools
2. Queries LLM with tool schemas
3. LLM returns function calls
4. Converts to structured `Plan` with steps

**Design Decisions**:

- Uses OpenAI function calling for structured outputs
- Temperature=0.3 for more deterministic plans
- Tool constraints enforced at query time
- Plans are immutable once created

**Tradeoffs**:

- ✅ Structured, type-safe plans
- ✅ Easy to audit and replay
- ❌ Requires LLM API call (latency + cost)
- ❌ Limited to sequential plans (no DAG yet)

### 2. Executor

**Responsibility**: Execute plans step-by-step with retries and caching.

**Flow**:

1. Iterate through plan steps
2. For each step:
   - Check cache (by tool + args hash)
   - If miss, execute tool
   - Retry on transient failures with exponential backoff
   - Cache successful results
3. Aggregate results and compute costs

**Design Decisions**:

- Sequential execution (no parallelism yet)
- Exponential backoff: `min(0.5 * 2^attempt, 10.0) + jitter`
- Cache TTL: 5 minutes (configurable)
- Stop on first failure (fail-fast)

**Tradeoffs**:

- ✅ Simple, predictable execution
- ✅ Caching reduces duplicate work
- ✅ Retries improve reliability
- ❌ Sequential limits throughput
- ❌ No partial recovery on failure

### 3. Tool Registry

**Responsibility**: Manage available tools and their schemas.

**Design**:

- Each tool implements `BaseTool` interface
- Tools self-register on import
- Version and schema stored in `ToolSpec`
- OpenAI format conversion for function calling

**Security**:

- Input validation against schema
- Timeouts per tool
- `http_fetch` blocks private IPs
- Size limits on responses

**Extensibility**:

- New tools: subclass `BaseTool`, register
- Schemas follow JSON Schema
- Can add auth/rate-limits per tool

### 4. Session Store

**Responsibility**: Persist session state in Redis.

**Data Model**:

```python
Session {
  id: str
  started_at: datetime
  ttl_s: int
  context: dict
  history: list[dict]
  total_tokens: int
  total_cost_usd: float
}
```

**Operations**:

- Create: Generate ID, set TTL
- Get: Retrieve by ID
- Update: Append history, update counters
- Delete: Expire session

**Tradeoffs**:

- ✅ Fast, low-latency
- ✅ TTL handles cleanup
- ❌ Volatile (lost on Redis restart)
- ❌ No cross-DC replication (yet)

## Governance

### Authentication & RBAC

**API Key Format**: `{key_id}.{hmac_signature}`

**Storage**: Redis hash per key:

```
apikey:{key_id} -> {role, created_at, status, name?}
```

**Validation**:

1. Parse `Authorization: Bearer {key}`
2. Verify HMAC signature
3. Check Redis for key data
4. Enforce role on protected endpoints

**Roles**:

- `admin`: Can create keys, access admin endpoints
- `developer`: Full tool access
- `client`: Standard access

### Rate Limiting

**Algorithm**: Sliding window with ZSET in Redis

**Key**: `rl:{api_key_id}`

**Logic**:

1. Remove entries older than window (1 second)
2. Count entries in window
3. If count >= QPS limit, check burst
4. If within burst, allow; else block
5. Add current timestamp to ZSET

**Tuning**:

- `RATE_LIMIT_QPS`: requests per second
- `RATE_LIMIT_BURST`: max burst above QPS

**Tradeoffs**:

- ✅ Accurate, fair
- ✅ Per-key isolation
- ❌ Redis latency on every request
- ❌ No distributed rate limiting (single Redis)

### Token Metering

**Pricing Map**:

```python
{
  "gpt-4o-mini": {
    "input": $0.00015 / 1K tokens,
    "output": $0.00060 / 1K tokens
  }
}
```

**Calculation**:

```python
cost = (tokens_in / 1000) * price_input + (tokens_out / 1000) * price_output
```

**Tracking**:

- Per request: in response
- Per session: cumulative in Session
- Global: Prometheus counter

### Data Masking

**Patterns**:

- Email: `user@domain.com` → `***@domain.com`
- API keys: `sk-abc123def456` → `sk-abc123***`
- Credit card: `1234-5678-9012-3456` → `****-****-****-3456`

**Application**:

- Before logging
- Before audit events
- On session read endpoints

**Sensitive Keys**: password, secret, token, api_key, etc.

### Audit Logging

**Event Structure**:

```python
AuditEvent {
  timestamp, api_key_id, actor_role, route, method, status,
  session_id?, masked_input_hash, tokens_in, tokens_out,
  cost_usd, ip, trace_id, duration_ms
}
```

**Flow**:

1. Middleware captures request/response
2. Mask sensitive data
3. Produce to Kafka `audit.logs`
4. Consumer processes for rollups/alerts

**Tradeoffs**:

- ✅ Immutable, tamper-proof
- ✅ Async (doesn't block requests)
- ❌ Kafka dependency
- ❌ No real-time queries (need to consume)

### Idempotency

**Storage**: Redis with `SETNX`

**Key**: `idempotency:{key}`

**Flow**:

1. Check if key exists → return cached response
2. Execute request
3. Store response with TTL (24h)

**Tradeoffs**:

- ✅ Safe retries for clients
- ✅ Prevents duplicate work
- ❌ Memory overhead
- ❌ Only covers successful responses

## Observability

### Tracing

**Spans**:

- Request (entire lifecycle)
- Plan creation (LLM call)
- Execution (entire plan)
- Step execution (per tool)
- Tool execution (internal)

**Export**: OTLP → Collector → (Prometheus/Jaeger)

**Correlation**: `trace_id` in logs

### Metrics

**Key Metrics**:

- Request rate, latency (p50/p95)
- Rate limit blocks
- Token consumption, cost
- Cache hit rate
- Tool execution count, latency

**Exposition**: `/metrics` endpoint (Prometheus scrape)

### Logging

**Format**: JSON with structured fields

**Fields**: timestamp, level, logger, message, trace_id, session_id, exception?

**Output**: stdout (collected by container runtime)

## Data Flow

### Sequence: Plan → Execute

```
Client
  │
  └─▶ POST /v1/plan {session_id, goal}
       │
       ├─▶ [Auth Middleware] Validate API key
       ├─▶ [Rate Limit Middleware] Check rate limit
       │
       └─▶ PlanEndpoint
            │
            ├─▶ SessionStore.get(session_id)
            │
            └─▶ Planner.create_plan(goal, context, tools_allowed)
                 │
                 ├─▶ LLMProvider.complete(messages, tools)
                 │    │
                 │    └─▶ OpenAI API
                 │
                 └─▶ Parse tool calls → Plan
                      │
                      ├─▶ TokenMeter.calculate_cost()
                      ├─▶ Metrics.record_tokens()
                      ├─▶ SessionStore.update_tokens_cost()
                      │
                      └─▶ [Response] Plan {steps, rationale}
                           │
                           ├─▶ [Audit Middleware] Log to Kafka
                           └─▶ [Metrics Middleware] Record latency

Client
  │
  └─▶ POST /v1/execute {session_id, plan}
       │
       ├─▶ [Check Idempotency] Return cached if exists
       │
       └─▶ ExecuteEndpoint
            │
            ├─▶ Executor.execute_plan(session_id, plan)
            │    │
            │    └─▶ For each step in plan:
            │         │
            │         ├─▶ Cache.get(tool, args) → hit? return
            │         │
            │         ├─▶ ToolRegistry.get(tool).execute(args)
            │         │    │
            │         │    └─▶ [Retries with backoff]
            │         │
            │         ├─▶ Cache.set(tool, args, result)
            │         │
            │         └─▶ Metrics.record_tool_execution()
            │
            ├─▶ TokenMeter.calculate_cost()
            ├─▶ SessionStore.update_tokens_cost()
            ├─▶ SessionStore.append_history()
            │
            └─▶ [Response] ExecutionResult {steps, cost, duration}
                 │
                 └─▶ [Store Idempotency] Cache response
```

## Design Tradeoffs

### Sequential vs. Parallel Execution

**Current**: Sequential

**Rationale**:

- Simpler to implement and debug
- Tools often have dependencies
- Easier error handling (stop on first failure)

**Future**: DAG-based execution for independent steps

### Redis for State vs. PostgreSQL

**Current**: Redis

**Rationale**:

- Low latency for session reads/writes
- TTL for automatic cleanup
- Suitable for ephemeral session data

**Future**: Hybrid approach (Redis + Postgres for long-term history)

### Kafka for Audit vs. Direct DB Writes

**Current**: Kafka

**Rationale**:

- Decouples audit from request path (async)
- Immutable log semantics
- Enables streaming analytics

**Tradeoffs**:

- Adds operational complexity
- No immediate queries (need to consume)

### Function Calling vs. Prompt Engineering

**Current**: OpenAI function calling

**Rationale**:

- Structured, type-safe outputs
- Better adherence to tool schemas
- Easier to parse and validate

**Tradeoffs**:

- Vendor-specific (OpenAI)
- Requires recent models

## Security Considerations

### Input Validation

- All tool inputs validated against JSON schema
- Payload size limits (100KB for HTTP fetch)
- Deny lists for URLs (no localhost/private IPs)

### Authentication

- HMAC-signed keys (prevents forgery)
- Key status checks (can revoke)
- No plaintext secrets in logs

### Data Protection

- PII masking in logs/audit
- Secrets replaced in error messages
- CORS disabled by default

### Rate Limiting

- Per-key limits (prevents abuse)
- Burst allowance (handles spikes)
- Retry-After header (client-friendly)

## Performance Characteristics

### Latency Targets (p95)

- Health/readiness: < 10ms
- List tools: < 50ms
- Create session: < 100ms
- Plan (with LLM): < 2.5s
- Execute (1 tool): < 500ms
- Execute (cached): < 50ms

### Throughput

- Requests: ~1000 RPS per instance (limited by rate limiter)
- Sessions: ~10K concurrent (Redis memory-bound)
- Tools: ~100 executions/s per tool type

### Caching

- Cache hit rate: 60-80% for repeat queries
- Cache TTL: 5 minutes
- Memory overhead: ~1KB per cached result

## Scaling Strategy

### Horizontal Scaling

- API: Stateless, can run multiple instances
- Redis: Cluster mode for scale-out
- Kafka: Add more partitions
- Consumers: Scale consumer groups

### Vertical Scaling

- API: CPU-bound (LLM calls, JSON processing)
- Redis: Memory-bound (sessions + cache)
- Kafka: Disk I/O bound

### Bottlenecks

1. **LLM API**: External latency, rate limits
2. **Redis**: Single-threaded, memory limits
3. **Kafka**: Network throughput, partition count

## Future Enhancements

### Short-Term

- [ ] DAG-based executor for parallel tool execution
- [ ] Circuit breaker for failing tools
- [ ] Enhanced streaming (token-by-token LLM output)
- [ ] Multi-model support (Anthropic, Cohere)

### Medium-Term

- [ ] Multi-agent orchestration (delegating sub-goals)
- [ ] Tools marketplace (plugin system)
- [ ] Advanced retry strategies (bulkhead, rate limiting per tool)
- [ ] Distributed rate limiting (Redis Cluster)

### Long-Term

- [ ] Multi-cloud/multi-region deployment
- [ ] Feature flags and A/B testing framework
- [ ] Vectorstore integration (Pinecone, Weaviate)
- [ ] Policy engine (OPA-based governance)

## Monitoring & Alerting

### Key Metrics to Alert On

- Error rate > 1%
- p95 latency > 3s (plan/execute)
- Rate limit blocks > 100/min
- Cache hit rate < 40%
- Redis memory > 80%
- Kafka lag > 1000 messages

### Dashboards

**Grafana Dashboard** (`infra/grafana/dashboards/agenthub_overview.json`):

- Request rate by route/status
- Latency percentiles (p50/p95)
- Token consumption and cost
- Rate limit blocks
- Cache hit rate

## Operational Runbook

### Deployment

1. Build Docker image: `docker build -t agenthub:latest .`
2. Push to registry
3. Update `docker-compose.yml` or k8s manifests
4. Roll out with health checks

### Rollback

1. Revert to previous image tag
2. Restart services
3. Verify health endpoints

### Incident Response

**High Error Rate**:

- Check LLM API status
- Verify Redis/Kafka connectivity
- Review recent deployments

**High Latency**:

- Check LLM API latency
- Review tool execution times
- Check Redis memory usage

**Rate Limit Abuse**:

- Identify abusive API keys
- Revoke keys via admin endpoint
- Adjust rate limits if needed

## References

- [OpenTelemetry](https://opentelemetry.io/)
- [Prometheus](https://prometheus.io/)
- [Redpanda](https://redpanda.com/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
