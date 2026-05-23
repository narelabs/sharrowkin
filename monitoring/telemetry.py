"""OpenTelemetry integration for tracing cognitive phases."""

import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# Initialize Tracer Provider
provider = TracerProvider()

# Check if we should export to console (useful for local dev) or a backend like Jaeger
if os.getenv("SHARROWKIN_TRACING") == "console":
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)

trace.set_tracer_provider(provider)

# Get a tracer for the agent
agent_tracer = trace.get_tracer("sharrowkin.agent")

def get_tracer():
    """Return the global tracer for the agent."""
    return agent_tracer
