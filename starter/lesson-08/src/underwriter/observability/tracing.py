"""OpenTelemetry tracing for the underwriting workflow (lesson 7).

    OTEL_EXPORTER=none (default)   spans are created but go nowhere; near-zero cost
    OTEL_EXPORTER=console          print each finished span as JSON
    OTEL_EXPORTER=otlp             send to OTEL_EXPORTER_OTLP_ENDPOINT (Jaeger, Tempo, …);
                                   needs `uv sync --extra otel`
    `underwriter trace <app>`      an in-memory exporter, printed as a tree

The span tree for one application:

    underwrite APP-002                       application, decision, reason codes
    ├── node income / checks / analyze / …   attempts, outcome (ok, retried, failed)
    │   ├── check credit_bureau              status, required, latency
    │   ├── retrieve                         k, results, abstained
    │   └── chat mock-underwriter-v1         gen_ai.* model and token attributes
    │       └── tool check_policy            outcome
    └── node engine                          recommendation, overridden

Two rules:

1. **No personal data in spans.** Applicant names, ids, emails and addresses never
   become attributes. Traces go to more systems and more people than the audit trail.
2. **Traces aren't the audit.** The audit trail is the business record, kept with the
   decision. Traces are operational telemetry: sampled, short-lived, for engineers.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, Status, StatusCode

SERVICE_NAME = "agentic-credit-underwriter"
_provider: TracerProvider | None = None
_memory: InMemorySpanExporter | None = None


def setup_tracing(exporter: str | None = None) -> InMemorySpanExporter | None:
    """Install the tracer provider once. Returns the in-memory exporter if used."""
    global _provider, _memory
    if _provider is not None:
        return _memory
    kind = (exporter or os.environ.get("OTEL_EXPORTER", "none")).lower()
    _provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    span_exporter: SpanExporter | None = None
    if kind == "console":
        span_exporter = ConsoleSpanExporter()
    elif kind == "memory":
        _memory = span_exporter = InMemorySpanExporter()
    elif kind == "otlp":  # pragma: no cover - needs a collector
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    elif kind != "none":
        raise ValueError(f"OTEL_EXPORTER must be none, console, memory or otlp, not {kind!r}")
    if span_exporter is not None:
        _provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(_provider)
    return _memory


def memory_exporter() -> InMemorySpanExporter:
    """An in-memory exporter on the active provider, added once (tests, `trace`)."""
    global _memory
    setup_tracing()
    if _memory is None:
        _memory = InMemorySpanExporter()
        _provider.add_span_processor(SimpleSpanProcessor(_memory))
    return _memory


def tracer() -> trace.Tracer:
    setup_tracing()
    return trace.get_tracer("underwriter")


@contextmanager
def span(name: str, **attributes) -> Iterator[Span]:
    """A span with attributes; None values are dropped.

    An exception marks the span as an error with a *redacted* description and an
    `error.type`, then propagates. OpenTelemetry's own exception recording is off: it
    would store the raw message and stack trace, which can carry personal data.
    """
    with tracer().start_as_current_span(name, record_exception=False,
                                        set_status_on_exception=False) as s:
        set_attrs(s, **attributes)
        try:
            yield s
        except Exception as exc:
            mark_error(s, f"{type(exc).__name__}: {exc}")
            s.set_attribute("error.type", type(exc).__name__)
            raise


def set_attrs(s: Span, **attributes) -> None:
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = [str(v) for v in value]
        elif not isinstance(value, (str, bool, int, float)):
            value = str(value)
        s.set_attribute(key.replace("__", "."), value)


_DIGITS = re.compile(r"\d{4,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def redact(text: str | None) -> str | None:
    """Safety net for free-text attributes (error messages): mask long digit runs and
    emails. The real fix is never to put personal data in a message; this catches
    the ones we miss."""
    if text is None:
        return None
    return _DIGITS.sub("<digits>", _EMAIL.sub("<email>", text))  # emails first


def mark_error(s: Span, description: str) -> None:
    description = redact(description) or ""
    s.set_status(Status(StatusCode.ERROR, description))
