"""OpenTelemetry wiring for Lost & Found Desk.

Signals:
  * traces  -- FastAPI request spans (auto) plus explicit model-op spans.
  * metrics -- counters/histograms for model calls and business events.
  * logs    -- stdlib logging enriched with the active trace_id/span_id.

By default everything is exported to the console (stdout) so the app is fully
observable with zero infrastructure. Set ``OTEL_EXPORTER_OTLP_ENDPOINT`` to ship
OTLP/HTTP to a collector instead. Set ``LFD_TELEMETRY=0`` to disable entirely.

The whole module is defensive: if the OpenTelemetry SDK is missing or setup
fails, every public helper degrades to a no-op so the app keeps running.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger("lost_found_desk.telemetry")

SERVICE_NAME = "lost-found-desk"
SERVICE_VERSION = "0.2.0"

# Model-op outcomes recorded on metrics/spans.
OUTCOME_SUCCESS = "success"
OUTCOME_FALLBACK = "fallback"
OUTCOME_ERROR = "error"

_initialized = False
_enabled = False
_fastapi_instrumented = False

_trace_mod: Any = None  # opentelemetry.trace module, when available
_tracer: Any = None
_meter: Any = None
_model_calls: Any = None
_model_duration: Any = None
_counters: dict[str, Any] = {}
_providers: dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
class _TraceContextFormatter(logging.Formatter):
    """Formatter that injects the active OTel trace/span id into each record."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id = "-"
        span_id = "-"
        if _trace_mod is not None:
            span = _trace_mod.get_current_span()
            ctx = span.get_span_context() if span is not None else None
            if ctx is not None and getattr(ctx, "is_valid", False):
                trace_id = format(ctx.trace_id, "032x")
                span_id = format(ctx.span_id, "016x")
        record.otel_trace_id = trace_id
        record.otel_span_id = span_id
        return super().format(record)


def _setup_logging(level: int) -> None:
    """Attach one console handler to the ``lost_found_desk`` logger namespace.

    Scoping to our namespace (with ``propagate=False``) avoids duplicating
    uvicorn's own handlers while still enriching every app/service log line.
    """
    pkg_logger = logging.getLogger("lost_found_desk")
    pkg_logger.setLevel(level)
    already = any(getattr(h, "name", "") == "lfd-telemetry" for h in pkg_logger.handlers)
    if not already:
        handler = logging.StreamHandler(sys.stdout)
        handler.set_name("lfd-telemetry")
        handler.setFormatter(
            _TraceContextFormatter(
                "%(asctime)s %(levelname)-7s "
                "trace_id=%(otel_trace_id)s span_id=%(otel_span_id)s "
                "%(name)s: %(message)s"
            )
        )
        pkg_logger.addHandler(handler)
    pkg_logger.propagate = False


def get_logger(name: str = "lost_found_desk.app") -> logging.Logger:
    return logging.getLogger(name)


# --------------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------------- #
def _telemetry_disabled() -> bool:
    return os.getenv("LFD_TELEMETRY", "1").strip().lower() in {"0", "false", "no", "off"}


def _otlp_endpoint() -> str | None:
    return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or None


def setup_telemetry(app: Any = None, service_name: str = SERVICE_NAME) -> None:
    """Initialize tracing, metrics, and trace-correlated logging (idempotent)."""
    global _initialized, _enabled, _trace_mod, _tracer, _meter
    global _model_calls, _model_duration

    if _initialized:
        if app is not None and _enabled:
            _instrument_fastapi(app)
        return

    log_level = getattr(logging, os.getenv("LFD_LOG_LEVEL", "INFO").upper(), logging.INFO)

    if _telemetry_disabled():
        _setup_logging(log_level)
        _initialized = True
        logger.info("telemetry disabled via LFD_TELEMETRY")
        return

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        # Concrete exporters are imported lazily in _make_exporters().
    except Exception:
        _setup_logging(log_level)
        _initialized = True
        logger.warning("OpenTelemetry SDK unavailable; running without telemetry", exc_info=True)
        return

    _trace_mod = trace
    _setup_logging(log_level)

    resource = Resource.create({"service.name": service_name, "service.version": SERVICE_VERSION})
    endpoint = _otlp_endpoint()
    span_exporter, metric_exporter, exporter_kind = _make_exporters(endpoint)

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    interval_ms = int(os.getenv("LFD_OTEL_METRIC_INTERVAL_MS", "60000"))
    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=interval_ms)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)

    _providers["tracer"] = tracer_provider
    _providers["meter"] = meter_provider

    _tracer = trace.get_tracer(service_name, SERVICE_VERSION)
    _meter = metrics.get_meter(service_name, SERVICE_VERSION)
    _model_calls = _meter.create_counter(
        "lfd.model.calls",
        unit="1",
        description="Model operations by op and outcome (success/fallback/error).",
    )
    _model_duration = _meter.create_histogram(
        "lfd.model.duration",
        unit="s",
        description="Model operation wall-clock duration in seconds.",
    )

    _enabled = True
    _initialized = True
    if app is not None:
        _instrument_fastapi(app)
    logger.info(
        "telemetry initialized: traces+metrics via %s exporter, metric interval=%dms",
        exporter_kind,
        interval_ms,
    )


def _make_exporters(endpoint: str | None) -> tuple[Any, Any, str]:
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            return OTLPSpanExporter(), OTLPMetricExporter(), "otlp"
        except Exception:
            logger.warning(
                "OTLP endpoint set but OTLP exporter unavailable; falling back to console",
                exc_info=True,
            )
    return ConsoleSpanExporter(), ConsoleMetricExporter(), "console"


def _instrument_fastapi(app: Any) -> None:
    global _fastapi_instrumented
    if _fastapi_instrumented:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        _fastapi_instrumented = True
        logger.info("FastAPI request tracing enabled")
    except Exception:
        logger.warning("FastAPI instrumentation unavailable", exc_info=True)


def shutdown_telemetry() -> None:
    """Flush and shut down providers so buffered spans/metrics are exported."""
    for provider in _providers.values():
        for method in ("force_flush", "shutdown"):
            try:
                getattr(provider, method)()
            except Exception:  # pragma: no cover - best effort on teardown
                pass


# --------------------------------------------------------------------------- #
# Public instrumentation helpers (all no-op when telemetry is off)
# --------------------------------------------------------------------------- #
def get_tracer() -> Any:
    if _trace_mod is not None:
        return _trace_mod.get_tracer(SERVICE_NAME, SERVICE_VERSION)
    return _NoopTracer()


def record_model_call(op: str, mode: str, outcome: str, duration_s: float) -> None:
    attrs = {"lfd.model.op": op, "lfd.model.mode": mode, "lfd.model.outcome": outcome}
    if _model_calls is not None:
        _model_calls.add(1, attrs)
    if _model_duration is not None:
        _model_duration.record(duration_s, attrs)


def increment(name: str, value: int = 1, attributes: dict[str, Any] | None = None) -> None:
    """Increment a named business counter (lazily created)."""
    if _meter is None:
        return
    counter = _counters.get(name)
    if counter is None:
        counter = _meter.create_counter(name, unit="1", description=f"Lost & Found Desk: {name}")
        _counters[name] = counter
    counter.add(value, attributes or {})


@contextmanager
def model_span(op: str, mode: str) -> Iterator[Any]:
    """Span around a model op, timing it and recording metrics by outcome.

    Use ``span.set_attribute('lfd.model.outcome', ...)`` to label the result;
    defaults to success, or error if the block raises.
    """
    tracer = get_tracer()
    start = time.perf_counter()
    outcome_holder = {"outcome": OUTCOME_SUCCESS}
    # We record the exception + ERROR status explicitly in the except branch,
    # so disable the SDK's automatic on-exit recording to avoid a duplicate
    # 'exception' event when the error propagates out of the span.
    with tracer.start_as_current_span(
        f"model.{op}", record_exception=False, set_status_on_exception=False
    ) as span:
        _set_attr(span, "lfd.model.op", op)
        _set_attr(span, "lfd.model.mode", mode)
        try:
            yield span
        except Exception:
            outcome_holder["outcome"] = OUTCOME_ERROR
            _record_exception(span)
            record_model_call(op, mode, OUTCOME_ERROR, time.perf_counter() - start)
            raise
        else:
            outcome = _read_outcome(span, default=OUTCOME_SUCCESS)
            outcome_holder["outcome"] = outcome
            record_model_call(op, mode, outcome, time.perf_counter() - start)


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """Generic span context manager for business operations."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as sp:
        for k, v in (attributes or {}).items():
            _set_attr(sp, k, v)
        yield sp


def set_span_attribute(sp: Any, key: str, value: Any) -> None:
    _set_attr(sp, key, value)


# --------------------------------------------------------------------------- #
# Internal helpers / no-op fallbacks
# --------------------------------------------------------------------------- #
def _set_attr(span: Any, key: str, value: Any) -> None:
    try:
        span.set_attribute(key, value)
    except Exception:  # pragma: no cover
        pass


def _read_outcome(span: Any, default: str) -> str:
    # SDK spans expose attributes as a mappingproxy/BoundedAttributes (not a
    # dict), so read via .get() rather than an isinstance(dict) check.
    attrs = getattr(span, "attributes", None)
    if attrs is not None:
        try:
            value = attrs.get("lfd.model.outcome")
        except Exception:
            value = None
        if value is not None:
            return str(value)
    return default


def _record_exception(span: Any) -> None:
    try:
        from opentelemetry.trace import Status, StatusCode

        exc = sys.exc_info()[1]
        if exc is not None:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception:  # pragma: no cover
        pass


class _NoopSpan:
    attributes: dict[str, Any] = {}

    def set_attribute(self, *_a: Any, **_k: Any) -> None: ...
    def add_event(self, *_a: Any, **_k: Any) -> None: ...
    def record_exception(self, *_a: Any, **_k: Any) -> None: ...
    def set_status(self, *_a: Any, **_k: Any) -> None: ...
    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *_a: Any) -> bool:
        return False


class _NoopTracer:
    def start_as_current_span(self, *_a: Any, **_k: Any) -> _NoopSpan:
        return _NoopSpan()
