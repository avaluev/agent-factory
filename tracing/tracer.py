"""
Tracer — Singleton that manages span lifecycle.

Usage patterns:

1. Context manager (preferred — auto-closes on success or error):
       tracer = Tracer.instance()
       with tracer.span(SpanType.TOOL_CALL, "my_tool", input_data={...}) as span:
           result = do_work()
           span.output_data = {"result": result}

2. Manual start/end (when you need to set output_data mid-flight):
       span = tracer.start_span(SpanType.LLM_CALL, "claude", ...)
       response = await call_llm()
       tracer.end_span(span, input_tokens=100, output_tokens=50, cost_usd=0.001)

Span nesting works automatically via a thread-local stack.
Any span started while another is active becomes its child.
"""
import uuid
import logging
import threading
from contextlib import contextmanager
from datetime import datetime

from tracing.models import TraceSpan, SpanType, SpanStatus
from tracing.store import TraceStore

logger = logging.getLogger(__name__)


class Tracer:
    _instance: "Tracer | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self._store = TraceStore()
        # Thread-local so concurrent agents don't clobber each other
        self._local = threading.local()

    @classmethod
    def instance(cls) -> "Tracer":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── trace context ──────────────────────────────────────────────
    def _get_trace_id(self) -> str | None:
        return getattr(self._local, "trace_id", None)

    def _set_trace_id(self, tid: str | None):
        self._local.trace_id = tid

    def _get_stack(self) -> list[str]:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        return self._local.stack

    # ── span lifecycle ─────────────────────────────────────────────
    def start_span(
        self,
        span_type: SpanType,
        name: str,
        *,
        input_data: dict | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> TraceSpan:
        """Create a span and push it onto the nesting stack."""
        stack = self._get_stack()
        trace_id = self._get_trace_id() or uuid.uuid4().hex[:16]
        # If this is the first span, it sets the trace_id for the session
        if not self._get_trace_id():
            self._set_trace_id(trace_id)

        parent_id = stack[-1] if stack else None

        span = TraceSpan(
            trace_id=trace_id,
            parent_id=parent_id,
            span_type=span_type,
            name=name,
            input_data=input_data or {},
            model=model,
            provider=provider,
        )
        stack.append(span.id)
        return span

    def end_span(
        self,
        span: TraceSpan,
        *,
        status: SpanStatus = SpanStatus.SUCCESS,
        error: str | None = None,
        output_data: dict | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        decision_reasoning: str | None = None,
    ) -> None:
        """Close a span, compute duration, persist."""
        span.ended_at = datetime.now().isoformat()
        span.status = status

        # Duration
        try:
            start = datetime.fromisoformat(span.started_at)
            end = datetime.fromisoformat(span.ended_at)
            span.duration_ms = (end - start).total_seconds() * 1000
        except (ValueError, TypeError):
            pass

        # Populate fields
        if output_data is not None:
            span.output_data = output_data
        if error is not None:
            span.error = error
        if input_tokens:
            span.input_tokens = input_tokens
        if output_tokens:
            span.output_tokens = output_tokens
        if cost_usd:
            span.cost_usd = cost_usd
        if decision_reasoning is not None:
            span.decision_reasoning = decision_reasoning

        # Pop stack
        stack = self._get_stack()
        if stack and stack[-1] == span.id:
            stack.pop()

        # If stack is now empty, clear the trace_id so next top-level op gets a fresh one
        if not stack:
            self._set_trace_id(None)

        # Persist
        self._store.save(span)

    @contextmanager
    def span(
        self,
        span_type: SpanType,
        name: str,
        *,
        input_data: dict | None = None,
        model: str | None = None,
        provider: str | None = None,
    ):
        """
        Context manager. Yields the span so you can mutate output_data inside.
        On normal exit → SUCCESS. On exception → ERROR (re-raises).
        """
        s = self.start_span(
            span_type, name,
            input_data=input_data, model=model, provider=provider,
        )
        try:
            yield s
            # Caller may have set s.output_data, s.cost_usd etc directly
            self.end_span(
                s,
                status=SpanStatus.SUCCESS,
                output_data=s.output_data,
                input_tokens=s.input_tokens,
                output_tokens=s.output_tokens,
                cost_usd=s.cost_usd,
                decision_reasoning=s.decision_reasoning,
            )
        except Exception as exc:
            self.end_span(s, status=SpanStatus.ERROR, error=str(exc))
            raise

    # ── convenience ────────────────────────────────────────────────
    @property
    def store(self) -> TraceStore:
        return self._store
