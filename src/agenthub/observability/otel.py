"""OpenTelemetry tracing setup."""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from agenthub.config import settings

_tracer_provider: TracerProvider | None = None


def setup_tracing() -> None:
    """Initialize OpenTelemetry tracing."""
    global _tracer_provider

    resource = Resource.create(
        {
            "service.name": "agenthub",
            "service.version": "0.1.0",
            "deployment.environment": settings.env,
        }
    )

    _tracer_provider = TracerProvider(resource=resource)

    # OTLP exporter
    otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
    span_processor = BatchSpanProcessor(otlp_exporter)
    _tracer_provider.add_span_processor(span_processor)

    trace.set_tracer_provider(_tracer_provider)


def get_tracer(name: str = "agenthub") -> trace.Tracer:
    """Get a tracer instance."""
    return trace.get_tracer(name)


def instrument_fastapi(app: Any) -> None:
    """Instrument FastAPI app with OpenTelemetry."""
    FastAPIInstrumentor.instrument_app(app)

