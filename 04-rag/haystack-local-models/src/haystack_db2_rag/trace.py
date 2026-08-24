"""Per-component progress events, taken from Haystack's own tracing hook.

Both pipelines are slow enough (~50 s to ingest, ~10 s to answer) that a UI needs to
show what is happening while it happens. Haystack already opens a span around every
component it runs — `haystack.component.run`, tagged with the component's name and
class — so we register a tracer and forward those spans as events.

That matters for honesty: the UI reports the components of the *real* Pipeline, running
exactly as ingest.py and search.py build it. Nothing here decomposes or re-implements
the pipeline to get progress out of it.

Usage:

    enable_step_tracing()               # once, at process start
    events = queue.Queue()
    with collecting(events):            # scoped to THIS thread
        ingest_pdf(path)                # events lands step dicts as they happen

The Haystack tracer is process-global, so events are routed by thread id: a span raised
on a thread with no queue registered is dropped. This is a single-user local demo; two
concurrent jobs on separate threads stay separate, and that is as far as it goes.
"""

import contextlib
import queue
import threading
import time
from typing import Any

from haystack.tracing import Span, Tracer, enable_tracing

COMPONENT_SPAN = "haystack.component.run"

# thread id -> the queue collecting that thread's step events
_queues: dict[int, queue.Queue] = {}


@contextlib.contextmanager
def collecting(events: queue.Queue):
    """Route this thread's component events into `events` for the duration of the block."""
    ident = threading.get_ident()
    _queues[ident] = events
    try:
        yield events
    finally:
        _queues.pop(ident, None)


def summarize(output: Any) -> str:
    """One short line describing what a component produced.

    The full output holds document text and 384-float embeddings, so it is measured and
    thrown away here rather than kept or forwarded.
    """
    if not isinstance(output, dict):
        return ""
    if "documents_written" in output:
        return f"{output['documents_written']} chunks written"
    if "documents" in output:
        return f"{len(output['documents'])} chunks"
    if "replies" in output:
        text = output["replies"][0].text if output["replies"] else ""
        return f"{len(text.split())} words"
    if "embedding" in output:
        return f"{len(output['embedding'])}-dimension vector"
    if "prompt" in output:
        prompt = output["prompt"]
        return f"{len(prompt)} message" if isinstance(prompt, list) else "prompt built"
    return ""


class StepSpan(Span):
    """A span for one component run. Records what the component produced, then reports
    elapsed time when the component finishes."""

    def __init__(self, events: queue.Queue, name: str, component_type: str):
        self.events = events
        self.name = name
        self.type = component_type
        self.detail = ""
        self.started = time.perf_counter()

    def set_tag(self, key: str, value: Any) -> None:
        pass

    def set_content_tag(self, key: str, value: Any) -> None:
        # Overriding this bypasses Haystack's content-tracing opt-in, which is what the
        # base class documents as the way to handle content yourself. We only ever keep
        # a count derived from it — see summarize().
        if key == "haystack.component.output":
            self.detail = summarize(value)

    def finish(self, error: str | None = None) -> None:
        self.events.put({
            "phase": "error" if error else "done",
            "name": self.name,
            "type": self.type,
            "elapsed": round(time.perf_counter() - self.started, 2),
            "detail": error or self.detail,
        })


class _Ignored(Span):
    """A span we are not reporting on (a pipeline-level span, or a thread with no queue)."""

    def set_tag(self, key: str, value: Any) -> None:
        pass


class StepTracer(Tracer):
    """Forwards component spans to the queue registered for the current thread."""

    def __init__(self):
        self._current: dict[int, Span] = {}

    @contextlib.contextmanager
    def trace(self, operation_name: str, tags: dict[str, Any] | None = None, parent_span=None):
        events = _queues.get(threading.get_ident())
        if events is None or operation_name != COMPONENT_SPAN:
            yield _Ignored()
            return

        tags = tags or {}
        span = StepSpan(
            events,
            name=tags.get("haystack.component.name", operation_name),
            component_type=tags.get("haystack.component.type", ""),
        )
        events.put({"phase": "start", "name": span.name, "type": span.type})
        self._current[threading.get_ident()] = span
        try:
            yield span
        except Exception as error:
            span.finish(error=f"{type(error).__name__}: {error}")
            raise
        else:
            span.finish()
        finally:
            self._current.pop(threading.get_ident(), None)

    def current_span(self) -> Span | None:
        return self._current.get(threading.get_ident())


def enable_step_tracing() -> None:
    """Install the tracer. Harmless when no queue is registered — every span is dropped."""
    enable_tracing(StepTracer())
