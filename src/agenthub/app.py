"""FastAPI application factory with improved error handling and headers."""

import time
import traceback
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException

from agenthub.api.routes import api_router
from agenthub.config import settings
from agenthub.deps import get_client_ip, get_redis
from agenthub.governance.audit import audit_logger
from agenthub.governance.rate_limiter import check_rate_limit
from agenthub.models.errors import create_error_response
from agenthub.observability import get_tracer, metrics, setup_logging, setup_tracing
from agenthub.observability.otel import instrument_fastapi

# Import tools to register them
import agenthub.tools.builtin_ads_metrics_mock  # noqa: F401
import agenthub.tools.builtin_http  # noqa: F401
import agenthub.tools.builtin_retrieve_doc  # noqa: F401
import agenthub.tools.builtin_search  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Lifespan event handler."""
    # Startup
    setup_logging()
    setup_tracing()

    yield

    # Shutdown
    audit_logger.close()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="AgentHub",
        description="Production-ready agentic orchestrator with governance and observability",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Instrument with OpenTelemetry
    instrument_fastapi(app)

    # Exception handlers for standardized error responses
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Handle HTTP exceptions with standardized format."""
        tracer = get_tracer()
        span = tracer.start_span("error_handler")
        trace_id = format(span.get_span_context().trace_id, "032x")
        span.end()

        error = create_error_response(
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
            trace_id=trace_id,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=error.model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Handle validation errors with standardized format."""
        tracer = get_tracer()
        span = tracer.start_span("validation_error")
        trace_id = format(span.get_span_context().trace_id, "032x")
        span.end()

        error = create_error_response(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            trace_id=trace_id,
            details={"errors": exc.errors()},
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error.model_dump(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions with standardized format."""
        tracer = get_tracer()
        span = tracer.start_span("exception_handler")
        trace_id = format(span.get_span_context().trace_id, "032x")
        span.end()

        # Log the full exception
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")

        error = create_error_response(
            code="INTERNAL_ERROR",
            message="An internal error occurred",
            trace_id=trace_id,
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error.model_dump(),
        )

    # Rate limiting middleware with headers
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):  # type: ignore
        """Rate limiting middleware with X-RateLimit-* headers."""
        # Skip rate limiting for health checks and metrics
        if request.url.path in ["/healthz", "/readyz", "/metrics"]:
            return await call_next(request)

        # Extract API key
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header.split(" ")[1]

            # Parse key_id
            try:
                key_id = api_key.split(".")[0]
                redis = await get_redis()

                # Check rate limit
                rate_limit_info = await check_rate_limit(redis, key_id)
                
                # Add rate limit headers to response
                response = await call_next(request)
                
                # Add headers
                for header_name, header_value in rate_limit_info.to_headers().items():
                    response.headers[header_name] = header_value
                
                # If not allowed, return 429
                if not rate_limit_info.allowed:
                    metrics.record_rate_limit(key_id)
                    
                    tracer = get_tracer()
                    span = tracer.start_span("rate_limit_exceeded")
                    trace_id = format(span.get_span_context().trace_id, "032x")
                    span.end()
                    
                    error = create_error_response(
                        code="RATE_LIMIT_EXCEEDED",
                        message="Rate limit exceeded",
                        trace_id=trace_id,
                        details={
                            "limit": rate_limit_info.limit,
                            "retry_after": rate_limit_info.retry_after,
                        },
                    )
                    
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content=error.model_dump(),
                        headers=rate_limit_info.to_headers(),
                    )
                
                return response
            except Exception:
                pass  # Continue if rate limit check fails

        return await call_next(request)

    # Metrics and audit logging middleware
    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):  # type: ignore
        """Metrics and audit logging middleware."""
        start_time = time.time()

        # Get trace ID
        tracer = get_tracer()
        span = tracer.start_span(request.url.path)
        trace_id = format(span.get_span_context().trace_id, "032x")

        # Add trace_id to request state for use in endpoints
        request.state.trace_id = trace_id

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        # Record metrics
        metrics.record_request(
            route=request.url.path,
            method=request.method,
            status=response.status_code,
            duration_ms=duration_ms,
        )

        # Audit logging (async, fire-and-forget)
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header.split(" ")[1]
                key_id = api_key.split(".")[0]

                await audit_logger.log(
                    api_key_id=key_id,
                    actor_role="unknown",
                    route=request.url.path,
                    method=request.method,
                    status=response.status_code,
                    trace_id=trace_id,
                    ip=get_client_ip(request),
                    duration_ms=duration_ms,
                )
        except Exception:
            pass  # Don't fail request if audit logging fails

        span.end()

        # Add trace ID to response headers
        response.headers["X-Trace-ID"] = trace_id

        return response

    # Include routers
    app.include_router(api_router)

    # Health endpoints
    @app.get("/healthz")
    async def health() -> dict:
        """Health check endpoint."""
        return {"status": "healthy"}

    @app.get("/readyz")
    async def readiness() -> dict:
        """Readiness check endpoint - validates dependencies."""
        try:
            redis = await get_redis()
            await redis.ping()
            return {"status": "ready", "redis": "ok"}
        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not ready", "error": str(e)},
            )

    @app.get("/metrics")
    async def prometheus_metrics() -> Response:
        """Prometheus metrics endpoint."""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    return app
