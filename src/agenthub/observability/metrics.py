"""Prometheus metrics."""

from prometheus_client import Counter, Histogram

# Request metrics
requests_total = Counter(
    "agenthub_requests_total",
    "Total HTTP requests",
    ["route", "method", "status"],
)

latency_histogram = Histogram(
    "agenthub_latency_ms",
    "Request latency in milliseconds",
    ["route"],
    buckets=[10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
)

# Rate limiting
rate_limited_total = Counter(
    "agenthub_rate_limited_total",
    "Total rate limit blocks",
    ["api_key_id"],
)

# Token and cost tracking
tokens_total = Counter(
    "agenthub_tokens_total",
    "Total tokens consumed",
    ["direction", "model"],
)

cost_usd_total = Counter(
    "agenthub_cost_usd_total",
    "Total cost in USD",
    ["model"],
)

# Cache metrics
cache_hits_total = Counter(
    "agenthub_cache_hits_total",
    "Total cache hits",
)

cache_misses_total = Counter(
    "agenthub_cache_misses_total",
    "Total cache misses",
)

# Tool execution
tool_executions_total = Counter(
    "agenthub_tool_executions_total",
    "Total tool executions",
    ["tool", "status"],
)

tool_latency_histogram = Histogram(
    "agenthub_tool_latency_ms",
    "Tool execution latency in milliseconds",
    ["tool"],
    buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
)


class Metrics:
    """Metrics collection helper."""

    def __init__(self) -> None:
        """Initialize metrics."""
        self.requests_total = requests_total
        self.latency_histogram = latency_histogram
        self.rate_limited_total = rate_limited_total
        self.tokens_total = tokens_total
        self.cost_usd_total = cost_usd_total
        self.cache_hits_total = cache_hits_total
        self.cache_misses_total = cache_misses_total
        self.tool_executions_total = tool_executions_total
        self.tool_latency_histogram = tool_latency_histogram

    def record_request(self, route: str, method: str, status: int, duration_ms: float) -> None:
        """Record a request."""
        self.requests_total.labels(route=route, method=method, status=str(status)).inc()
        self.latency_histogram.labels(route=route).observe(duration_ms)

    def record_rate_limit(self, api_key_id: str) -> None:
        """Record a rate limit block."""
        self.rate_limited_total.labels(api_key_id=api_key_id).inc()

    def record_tokens(self, direction: str, model: str, tokens: int) -> None:
        """Record token usage."""
        self.tokens_total.labels(direction=direction, model=model).inc(tokens)

    def record_cost(self, model: str, cost: float) -> None:
        """Record cost."""
        self.cost_usd_total.labels(model=model).inc(cost)

    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self.cache_hits_total.inc()

    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        self.cache_misses_total.inc()

    def record_tool_execution(
        self, tool: str, status: str, latency_ms: float
    ) -> None:
        """Record a tool execution."""
        self.tool_executions_total.labels(tool=tool, status=status).inc()
        self.tool_latency_histogram.labels(tool=tool).observe(latency_ms)


metrics = Metrics()

