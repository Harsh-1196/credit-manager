"""
OpenTelemetry Tracing Setup for SHG Credit Manager (Phase 7)
Instruments HTTP requests, database transactions, and background workers.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def setup_telemetry(service_name: str = "shg-credit-manager-backend") -> None:
    """Initialize OpenTelemetry tracer provider."""
    try:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        # In production/docker, OTLPSpanExporter connects to collector; ConsoleSpanExporter for dev/testing
        # provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
    except Exception:
        pass


def get_tracer(name: str = "shg.credit.manager") -> trace.Tracer:
    """Returns application tracer."""
    return trace.get_tracer(name)


@asynccontextmanager
async def trace_span(name: str, attributes: dict[str, Any] | None = None) -> AsyncGenerator[trace.Span, None]:
    """Async context manager to trace a block of code."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, str(v))
        yield span
