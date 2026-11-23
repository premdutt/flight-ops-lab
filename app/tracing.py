# app/tracing.py
from agent_framework.observability import configure_otel_providers
from opentelemetry import trace

def start_tracing():
    configure_otel_providers()      # reads the OTEL_* settings from the environment

def flush_tracing():
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush()      # short CLI runs can exit before traces are sent