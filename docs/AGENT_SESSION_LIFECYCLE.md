# Agent Session Lifecycle Design

## Overview

This document describes the complete lifecycle of an agent session in AgentHub, including state management, TTL/rehydration, idempotency, retries, circuit-breaker patterns, and dead letter queue handling.

## State Machine

```
┌─────────────┐
│   Created   │ ──────────┐
└─────────────┘           │
       │                  │
       │ plan()           │
       ▼                  │
┌─────────────┐           │
│  Planning   │           │ TTL Expiry
└─────────────┘           │
       │                  │
       │ execute()        │
       ▼                  │
┌─────────────┐           │
│  Executing  │           │
└─────────────┘           │
       │                  │
       │ complete         │
       ▼                  │
┌─────────────┐           │
│  Completed  │ ──────────┤
└─────────────┘           │
       │                  │
       │ (optional)       │
       ▼                  │
┌─────────────┐           │
│   Archived  │           │
└─────────────┘           │
                          │
                          ▼
                   ┌─────────────┐
                   │   Expired   │
                   └─────────────┘
```

### States

1. **Created**: Session initialized, no plan yet
2. **Planning**: Planner is generating execution plan
3. **Executing**: Executor is running plan steps
4. **Completed**: All steps finished (success or failure)
5. **Archived**: Session moved to cold storage
6. **Expired**: TTL reached, session purged

## Session Data Model

```python
Session {
    id: str                          # Unique identifier (urlsafe token)
    started_at: datetime              # Creation timestamp
    ttl_s: int                       # Time-to-live in seconds (default 86400)
    context: dict                    # User-provided context
    history: list[dict]              # Chronological event log
    total_tokens: int                # Cumulative tokens consumed
    total_cost_usd: float            # Cumulative cost in USD
    state: str                       # Current state (created, planning, etc.)
}
```

## TTL and Rehydration

### TTL Strategy

- **Default TTL**: 24 hours (86400 seconds)
- **Configurable per session**: Can be set at creation time
- **Extension**: Automatic on any session access
- **Cleanup**: Redis native expiration handles deletion

### Rehydration Flow

```
Client Request
    │
    └──> GET /v1/sessions/{id}
           │
           ├──> Redis HGETALL session:{id}
           │
           ├──> Check if exists
           │     │
           │     ├─[Yes]─> Parse JSON → Session object
           │     │            │
           │     │            └──> Extend TTL (EXPIRE)
           │     │                   │
           │     │                   └──> Return Session
           │     │
           │     └─[No]──> Return 404 (Session expired or never existed)
           │
           └──> (End)
```

### Extending TTL

Sessions are automatically extended on:

- Any read operation (`GET /v1/sessions/{id}`)
- Any write operation (append history, update counters)
- Plan or execute operations

## Idempotency

### Idempotency Key Flow

```
POST /v1/execute
Headers: Idempotency-Key: <uuid>
    │
    ├──> Check Redis: idempotency:{key}
    │      │
    │      ├─[Exists]──> Return cached response (200 OK)
    │      │               │
    │      │               └──> (Skip execution)
    │      │
    │      └─[Not Exists]──> Execute request
    │                          │
    │                          ├──> Store response: SETNX idempotency:{key}
    │                          │       TTL: 24 hours
    │                          │
    │                          └──> Return response
    │
    └──> (End)
```

### Idempotency Keys

- **Format**: Client-generated UUID or similar
- **Storage**: Redis with `SETNX` (set if not exists)
- **TTL**: 24 hours (configurable)
- **Scope**: Per endpoint (plan, execute, etc.)
- **Concurrency**: First request wins, others get cached result

### Endpoints with Idempotency

- `POST /v1/sessions` - Prevents duplicate session creation
- `POST /v1/plan` - Prevents duplicate plan generation
- `POST /v1/execute` - Prevents duplicate execution (most critical)

## Retry Strategy

### Executor Retry Logic

```python
def execute_step_with_retries(step):
    max_retries = 3
    base_backoff = 0.5  # seconds
    max_backoff = 10.0

    for attempt in range(max_retries):
        try:
            result = execute_tool(step.tool, step.args)
            return result  # Success

        except TransientError as e:
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                backoff = min(base_backoff * (2 ** attempt), max_backoff)
                jitter = random.uniform(0, backoff * 0.1)
                sleep(backoff + jitter)
                continue
            else:
                # Max retries reached
                return ToolResult(ok=False, error=str(e))

        except PermanentError as e:
            # Don't retry
            return ToolResult(ok=False, error=str(e))
```

### Retry Metadata

Stored in session history:

```json
{
  "type": "step_execution",
  "step_id": "step_0",
  "tool": "http_fetch",
  "attempt": 2,
  "result": "transient_error",
  "backoff_ms": 1000,
  "timestamp": "2025-10-11T12:34:56Z"
}
```

### Transient vs. Permanent Errors

**Transient (retry)**:

- Network timeouts
- HTTP 429 (rate limit)
- HTTP 5xx (server errors)
- Connection refused

**Permanent (don't retry)**:

- HTTP 4xx (client errors)
- Invalid input
- Tool not found
- Authorization failures

## Circuit Breaker

### Circuit Breaker States

```
    ┌─────────┐
    │  Closed │ ──────> [Normal Operation]
    └─────────┘
         │
         │ Failure Threshold
         ▼
    ┌─────────┐
    │  Open   │ ──────> [Reject Requests]
    └─────────┘
         │
         │ Timeout
         ▼
    ┌─────────┐
    │Half-Open│ ──────> [Test Recovery]
    └─────────┘
         │
         ├──[Success]──> Closed
         └──[Failure]──> Open
```

### Configuration (per tool)

```python
CircuitBreaker {
    failure_threshold: 5        # Failures before opening
    success_threshold: 2        # Successes to close
    timeout: 60                # Seconds in open state
    window: 10                 # Rolling window in seconds
}
```

### Implementation

```python
class CircuitBreaker:
    def __init__(self, tool_name):
        self.state = "closed"
        self.failures = 0
        self.last_failure = None

    def call(self, func, *args):
        if self.state == "open":
            if time.time() - self.last_failure > self.timeout:
                self.state = "half-open"
            else:
                raise CircuitOpenError("Circuit breaker is open")

        try:
            result = func(*args)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise

    def on_success(self):
        if self.state == "half-open":
            self.state = "closed"
        self.failures = 0

    def on_failure(self):
        self.failures += 1
        self.last_failure = time.time()

        if self.failures >= self.failure_threshold:
            self.state = "open"
```

## Dead Letter Queue (DLQ)

### When to Send to DLQ

- Exceeded max retries (3 attempts)
- Permanent errors that can't be recovered
- Malformed requests that passed validation
- Circuit breaker consistently tripping

### DLQ Event Structure

```json
{
  "event_type": "dead_letter",
  "timestamp": "2025-10-11T12:34:56Z",
  "original_topic": "agent.events",
  "original_payload": {
    "session_id": "abc123",
    "step_id": "step_0",
    "tool": "http_fetch",
    "args": {...}
  },
  "error": "Max retries exceeded: Connection timeout",
  "retry_count": 3,
  "first_attempt": "2025-10-11T12:30:00Z",
  "last_attempt": "2025-10-11T12:34:56Z",
  "circuit_breaker_state": "open"
}
```

### DLQ Processing

```
DLQ Consumer
    │
    ├──> Read event from dead.letter topic
    │
    ├──> Log to monitoring system (PagerDuty, etc.)
    │
    ├──> Store in DLQ database for analysis
    │
    ├──> Check if should retry (manual review)
    │     │
    │     ├─[Yes]──> Re-queue to original topic
    │     │
    │     └─[No]──> Mark as permanently failed
    │
    └──> Send alert to on-call
```

## Caching Strategy

### Cache Key Generation

```python
def make_cache_key(tool: str, args: dict) -> str:
    # Sort args for consistent hashing
    args_json = json.dumps(args, sort_keys=True)
    args_hash = hashlib.sha256(args_json.encode()).hexdigest()[:16]
    return f"cache:tool:{tool}:{args_hash}"
```

### Cache Invalidation

**Time-based**:

- TTL: 5 minutes (configurable per tool)
- Automatic expiration via Redis

**Version-based**:

- Tool version changes invalidate all caches for that tool
- Cache key includes tool version: `cache:tool:{name}:{version}:{args_hash}`

**Manual**:

- Admin endpoint: `DELETE /v1/admin/cache/{tool}`
- Clears all caches for a specific tool

### Cache Hit/Miss Flow

```
execute_step(tool, args)
    │
    ├──> Check cache: cache:tool:{tool}:{args_hash}
    │      │
    │      ├─[Hit]──> Return cached result
    │      │            │
    │      │            ├──> Metrics: cache_hits_total++
    │      │            └──> (Skip execution)
    │      │
    │      └─[Miss]──> Execute tool
    │                    │
    │                    ├──> Metrics: cache_misses_total++
    │                    │
    │                    ├──> Store result in cache (TTL)
    │                    │
    │                    └──> Return result
    │
    └──> (End)
```

## Concurrency and Race Conditions

### Session Creation

**Problem**: Multiple concurrent requests with same idempotency key

**Solution**: Redis `SETNX` (atomic)

```python
# Only first request succeeds
result = await redis.set(f"idempotency:{key}", value, nx=True, ex=ttl)
if not result:
    # Key already exists, return cached
    return await redis.get(f"idempotency:{key}")
```

### Step Execution

**Problem**: Same step executed multiple times

**Solution**: Step-level idempotency

```python
step_key = f"step:{session_id}:{step_id}"
if await redis.exists(step_key):
    return cached_result
```

### Rate Limiting

**Problem**: Race condition in sliding window counter

**Solution**: Redis sorted sets with atomic operations

```python
# Atomic: remove old + count + add
pipeline = redis.pipeline()
pipeline.zremrangebyscore(key, 0, now - window)
pipeline.zcard(key)
pipeline.zadd(key, {now: now})
results = await pipeline.execute()
```

## Monitoring and Alerts

### Key Metrics

- **Session States**:

  - `sessions_created_total`
  - `sessions_expired_total`
  - `sessions_active_gauge`

- **Retries**:

  - `tool_retries_total{tool, attempt}`
  - `tool_failures_total{tool, reason}`

- **Circuit Breaker**:

  - `circuit_breaker_state{tool, state}` (gauge)
  - `circuit_breaker_trips_total{tool}`

- **DLQ**:
  - `dlq_events_total{reason}`
  - `dlq_age_seconds{event_id}` (histogram)

### Alerts

**Critical**:

- Circuit breaker open for > 5 minutes
- DLQ events > 100/hour
- Session creation failures > 10/minute

**Warning**:

- Retry rate > 20% of requests
- Cache hit rate < 40%
- Session TTL extensions > 1000/minute

## Performance Characteristics

### Latency Targets

- **Session creation**: < 50ms (p95)
- **Session rehydration**: < 10ms (p95)
- **Idempotency check**: < 5ms (p95)
- **Cache hit**: < 5ms (p95)

### Throughput

- **Sessions**: 10K concurrent active sessions
- **Rehydration**: 10K ops/sec
- **Idempotency checks**: 50K ops/sec

### Resource Usage

- **Memory**: ~1MB per active session
- **Redis**: ~100KB per session + 1KB per cache entry
- **Kafka**: ~1KB per audit event

## Security Considerations

### Session Hijacking

- Session IDs are cryptographically random (urlsafe tokens)
- No predictable patterns
- Rate limiting prevents brute force

### Data Isolation

- Sessions are tenant-isolated via API key
- No cross-tenant queries
- Masked data in logs/audit

### TTL as Security

- Expired sessions are purged completely
- No residual data in Redis
- Audit logs retained separately (immutable)

## Future Enhancements

### Short-Term

- [ ] Distributed session store (Redis Cluster)
- [ ] Session snapshots for long-running workflows
- [ ] Priority queues for urgent sessions

### Medium-Term

- [ ] Multi-region session replication
- [ ] Session migration between regions
- [ ] Advanced circuit breaker (bulkhead pattern)

### Long-Term

- [ ] Session orchestration across multiple agents
- [ ] Workflow engine integration (Temporal, etc.)
- [ ] ML-based retry prediction
