# AgentHub

AgentHub is an agent orchestration platform for automated multi-step AI workflows. The system provides a governed runtime for AI agents, supporting planning, execution, and state management. It is designed for operational safety, cost efficiency, and observability in production environments.

## Overview

AgentHub is the control plane for large language model (LLM)–driven workflows. The platform manages agent planning and execution, applies governance controls (rate limiting, idempotency, token metering, auditing), and delivers end-to-end observability (metrics, tracing, dashboards).

Key capabilities:

- Multi-step orchestration with low latency at scale
- Predictable token and cost management
- Tenant-level isolation and access governance
- End-to-end workflow visibility

## Architecture

```mermaid
flowchart LR
  subgraph Client
    C[Client or Upstream Service]
  end

  C --> API[AgentHub API Service]

  subgraph Governance
    RL[Rate Limiter]
    IDEM[Idempotency Cache]
    TM[Token Meter]
    AUD[Audit Logger]
    MSK[Data Masking]
    RBAC[Auth & RBAC]
  end

  API --> RL --> IDEM --> TM --> AUD --> MSK --> RBAC --> Router[Router]

  subgraph Orchestration
    PLN[Planner]
    EXE[Executor]
    SSE[Event Stream (SSE)]
    CACHE[Cache]
  end

  Router --> PLN --> EXE --> SSE
  EXE --> CACHE

  subgraph Tools
    T1[Tool 1: Retrieval]
    T2[Tool 2: HTTP Fetch]
    T3[Tool 3: Ads Insights]
  end

  EXE --> T1
  EXE --> T2
  EXE --> T3

  subgraph Infra
    R[(Redis: State, Rate Limits, Cache)]
    K[(Kafka/Redpanda: Events, Audit, DLQ)]
    P[(Prometheus + Grafana)]
    O[(OpenTelemetry Tracing)]
    S3[(S3: Audit Rollups and Retention)]
  end

  PLN <--> R
  EXE <--> R
  RL <--> R
  IDEM <--> R
  TM <--> R
  AUD --> K --> S3
  API --> P
  API --> O
```

## How agenthub works

- **Request flow:** Requests are processed through a governance pipeline that enforces rate limits, idempotency, token metering, auditing, data masking, and role-based access control. After governance, the planner determines workflow steps; the executor runs the required tools.
- **Session state:** Redis stores persistent agent session data, including plans, step results, token usage, and cost. Sessions have time-to-live expiration and support rehydration to restore workflow context.
- **Governance:** The platform enforces per-tenant throughput and burst limits. API key lifecycle management includes issuing, rotating, and revoking. Audit events are masked for PII and secrets, streamed to Kafka, and rolled up to S3 for retention.
- **Reliability:** POST requests are idempotent via an `Idempotency-Key`. The system retries failed operations with exponential backoff and circuit breaking. Unrecoverable tool failures are routed to a dead-letter queue.
- **Observability:** Prometheus collects metrics for request latency, rate-limit rejections, circuit trips, dead-letter queue publications, cache hits, and token spending. OpenTelemetry traces include tenant ID, API key ID, session ID, tool, attempt count, and cache status.
- **Streaming:** Server-Sent Events (SSE) stream live updates for steps, tokens, and final messages. Heartbeats are sent every 15 seconds. Streams terminate gracefully when workflows complete.

## Features

- **Planner and executor:** LLM-powered planning with function calling and sequential execution
- **Tool registry:** Four built-in tools (search, http_fetch, retrieve_doc, ads_metrics_mock) with versioning
- **RBAC and authentication:** HMAC-signed API keys with role-based access control
- **Rate limiting:** Sliding window rate limiter with burst support
- **Token metering:** Tracks token usage and cost across models
- **Audit logging:** Immutable audit logs to Kafka with PII masking
- **Observability:** OpenTelemetry traces, Prometheus metrics, Grafana dashboards
- **Streaming:** Server-Sent Events for real-time updates
- **Session management:** Redis-backed sessions with TTL
- **Idempotency:** Idempotency keys for safe retries
- **Performance:** Result caching, retry with backoff, circuit breaking

## Quick start

### Prerequisites

- Docker and Docker Compose
- (Optional) Python 3.11 for local development

### 1. Clone and configure

```bash
git clone https://github.com/sarihammad/agenthub.git
cd agenthub
cp .env.example .env
# Edit .env and set your OpenAI API key
# OPENAI_API_KEY=sk-...
```

### 2. Start the stack

```bash
docker-compose up --build
```

Services started:

- API: `localhost:8080`
- Grafana: `localhost:3000` (admin/admin)
- Prometheus: `localhost:9090`
- Redis: `localhost:6379`
- Redpanda (Kafka): `localhost:9092`

### 3. Create an admin API key

To bootstrap an admin key (in production, use secure provisioning):

```bash
docker exec -it agenthub-api-1 python -c "
import asyncio
from agenthub.deps import get_redis
from agenthub.auth.api_keys import create_api_key
async def main():
    redis = await get_redis()
    key = await create_api_key(redis, 'admin', 'bootstrap_admin')
    print(f'Admin API Key: {key[\"api_key\"]}')
    await redis.close()
asyncio.run(main())
"
```

Save the admin API key for future use.

### 4. Example usage

#### Create API keys

```bash
export ADMIN_KEY="<admin_key_from_above>"
curl -X POST http://localhost:8080/v1/admin/api-keys \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"role": "client", "name": "demo_client"}'
```

Save the returned `api_key` as your client key.

#### Create a session

```bash
export CLIENT_KEY="<client_key>"
curl -X POST http://localhost:8080/v1/sessions \
  -H "Authorization: Bearer $CLIENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Save the `session_id`.

#### List available tools

```bash
curl http://localhost:8080/v1/tools \
  -H "Authorization: Bearer $CLIENT_KEY"
```

#### Create a plan

```bash
export SESSION_ID="<session_id>"
curl -X POST http://localhost:8080/v1/plan \
  -H "Authorization: Bearer $CLIENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "'$SESSION_ID'",
    "goal": "Get ROAS metrics for advertiser 123 over the last 7 days",
    "tools_allowed": ["ads_metrics_mock", "retrieve_doc"]
  }'
```

This returns a plan with steps and rationale.

#### Execute a plan

```bash
curl -X POST http://localhost:8080/v1/execute \
  -H "Authorization: Bearer $CLIENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "'$SESSION_ID'",
    "plan": {
      "steps": [
        {
          "tool": "ads_metrics_mock",
          "args": {
            "advertiser_id": "123",
            "metric": "roas",
            "date_range": "7d"
          }
        }
      ],
      "rationale": "Fetch ROAS for advertiser 123",
      "created_at": "'$(date -u +"%Y-%m-%dT%H:%M:%S")'",
      "estimated_tokens": 0
    }
  }'
```

#### Stream session events (SSE)

```bash
curl -N http://localhost:8080/v1/stream?session_id=$SESSION_ID \
  -H "Authorization: Bearer $CLIENT_KEY"
```

This streams events in real time with heartbeats every 15 seconds.

## Architecture reference

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design, sequence diagrams, and tradeoffs.

## API endpoints

| Method | Path                 | Auth  | Description                  |
| ------ | -------------------- | ----- | ---------------------------- |
| POST   | `/v1/sessions`       | Any   | Create a new session         |
| GET    | `/v1/sessions/{id}`  | Any   | Get session details (masked) |
| POST   | `/v1/plan`           | Any   | Create an execution plan     |
| POST   | `/v1/execute`        | Any   | Execute a plan               |
| GET    | `/v1/stream`         | Any   | Stream session events (SSE)  |
| GET    | `/v1/tools`          | Any   | List available tools         |
| POST   | `/v1/admin/api-keys` | Admin | Create or rotate API keys    |
| GET    | `/healthz`           | None  | Health check                 |
| GET    | `/readyz`            | None  | Readiness check              |
| GET    | `/metrics`           | None  | Prometheus metrics           |

## RBAC roles

- **admin:** Full access, can create API keys
- **developer:** Access to all tools and endpoints
- **client:** Access to sessions, planning, and execution

## Governance

### Rate limiting

- Default: 5 QPS with burst up to 10
- Returns `429 Too Many Requests` with `Retry-After` header
- Enforced per API key (sliding window)

### Token metering

- Tracks tokens per request and per session
- Calculates cost in USD based on model pricing
- Metrics exposed via Prometheus

### Data masking

PII and secrets are masked in logs and audit records:

- Email addresses (domain retained)
- AWS/API keys (prefix retained)
- Credit cards (last 4 digits retained)
- Configurable sensitive fields

### Audit logging

- All requests logged to Kafka topic `audit.logs`
- Fields: timestamp, API key, role, route, status, tokens, cost, IP, trace ID
- Logs are immutable and append-only

### Idempotency

- Use `Idempotency-Key` header on mutating endpoints
- Keys stored in Redis with 24h TTL
- Duplicate keys return cached response

## Observability

### Traces

- OpenTelemetry spans for requests, plan, steps, and LLM calls
- Exported to OTLP collector
- Trace IDs are present in logs for correlation

### Metrics

Metrics available at `/metrics`:

- `agenthub_requests_total`: Request count by route/status
- `agenthub_latency_ms`: Request latency histogram
- `agenthub_rate_limited_total`: Rate limit blocks
- `agenthub_tokens_total`: Token consumption
- `agenthub_cost_usd_total`: Total cost
- `agenthub_cache_hits_total`: Cache hit count
- `agenthub_tool_executions_total`: Tool execution count

### Dashboards

Grafana dashboard at `localhost:3000`:

- Request rate and latency (p50, p95)
- Token usage and cost tracking
- Rate limit blocks
- Cache hit rate

## Tools

### Built-in tools

1. `search(query)`: Mock web search
2. `http_fetch(url)`: Fetch HTTP(S) URLs with security controls
3. `retrieve_doc(doc_id)`: Retrieve from mock vectorstore
4. `ads_metrics_mock(advertiser_id, metric, date_range)`: Mock ad metrics

### Tool security

- `http_fetch` blocks localhost and private IPs
- All tools have timeouts and input validation
- Results are cached to reduce duplicate work

## Development

### Local setup

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
black --check src/ tests/
mypy src/
black src/ tests/
```

### Run locally without Docker

```bash
# Start Redis and Redpanda separately
python -m agenthub.server
```

## Service level objectives (SLOs)

- p95 latency < 300ms for non-LLM endpoints
- p95 latency < 2.5s for single-tool plans
- 99.9% success rate for well-formed requests

## Configuration

See `.env.example` for all configuration options.

Key settings:

- `OPENAI_API_KEY`: OpenAI API key
- `RATE_LIMIT_QPS`: Requests per second limit
- `SESSION_TTL_SECONDS`: Session expiration (default 24h)

## Troubleshooting

- **Rate limit exceeded:** Wait for the `Retry-After` duration or increase `RATE_LIMIT_QPS` in `.env`.
- **Session not found:** Sessions expire after `SESSION_TTL_SECONDS`. Create a new session.
- **OpenAI API errors:** Ensure `OPENAI_API_KEY` is set in `.env`. The planner requires a valid key.
- **Kafka/Redpanda connection errors:** Confirm Redpanda is running (`docker-compose ps`). Check logs (`docker-compose logs redpanda`).

## License

MIT License. See [LICENSE](LICENSE).

## Roadmap

- [ ] Multi-agent orchestration
- [ ] Tools marketplace with versioning
- [ ] Feature flags and A/B testing
- [ ] Advanced retry strategies (circuit breaker, bulkhead)
- [ ] Multi-cloud provider support (Anthropic, Cohere, etc.)
- [ ] Vectorstore integration (Pinecone, Weaviate)
- [ ] Enhanced streaming with token-by-token LLM output
