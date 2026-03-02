"""OpenTelemetry tracing initialization."""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from steward.core.logging import get_logger

logger = get_logger(component="tracing")
_configured = False


def configure_tracing() -> None:
    """Initialize OTEL provider and exporter once."""
    global _configured
    if _configured:
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "steward")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("tracing_initialized", mode="otlp", endpoint=endpoint)
    else:
        logger.info("tracing_initialized", mode="in_process")

    trace.set_tracer_provider(provider)
    _configured = True
