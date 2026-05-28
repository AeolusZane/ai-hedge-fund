"""Abstract executor contract for domain workflow runtimes.

Each domain (finance, bug-fix, ...) ships a WorkflowExecutor subclass that knows
how to take a domain-specific request, drive the workflow graph, and stream
progress events. The core /workflows/run route looks the executor up via the
registry and adapts its events into SSE.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

from sqlalchemy.orm import Session


ProgressCallback = Callable[["ProgressEvent"], None]


@dataclass
class ProgressEvent:
    """Single progress tick emitted by an executor.

    `node_id` identifies the React Flow node that produced the event (when
    applicable). `payload` is free-form per-domain data forwarded to the UI.
    """

    node_id: Optional[str]
    status: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutorContext:
    """Per-run dependencies handed to an executor.

    Kept narrow on purpose: anything the executor needs from the platform
    (DB session, resolved API keys, cancellation, progress emitter) flows
    through here so executors stay decoupled from FastAPI internals.
    """

    db: Session
    api_keys: dict[str, str]
    emit: ProgressCallback
    is_cancelled: Callable[[], bool]


class WorkflowExecutor(ABC):
    """Domain-specific workflow runtime."""

    #: Unique domain id, e.g. "finance". Must match DomainPack.id on the frontend.
    domain: str

    @abstractmethod
    async def run(self, request: dict[str, Any], context: ExecutorContext) -> dict[str, Any]:
        """Execute the workflow and return its final result payload.

        Progress events should be emitted via `context.emit` during execution.
        The returned dict becomes the `results` field of the FlowRun row and
        the `data` payload of the final SSE complete event.
        """

    async def stream(
        self, request: dict[str, Any], context: ExecutorContext
    ) -> AsyncIterator[ProgressEvent]:
        """Optional override for executors that want to yield events directly.

        Default implementation just calls `run` and yields nothing — subclasses
        that prefer a generator-style API can override this instead of `run`.
        """
        raise NotImplementedError
