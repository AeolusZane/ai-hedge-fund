"""Domain executor registry.

Domain packages import and call `executor_registry.register(MyExecutor())`
at module load time (typically from `app.backend.domains.<id>.__init__`).
The core run route resolves an executor by domain id via this registry.
"""
from __future__ import annotations

from typing import Iterator

from app.backend.core.executors.base import WorkflowExecutor


class ExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, WorkflowExecutor] = {}

    def register(self, executor: WorkflowExecutor) -> None:
        if not getattr(executor, "domain", None):
            raise ValueError(f"Executor {executor!r} is missing a `domain` id")
        if executor.domain in self._executors:
            raise ValueError(f"Executor for domain {executor.domain!r} already registered")
        self._executors[executor.domain] = executor

    def get(self, domain: str) -> WorkflowExecutor:
        try:
            return self._executors[domain]
        except KeyError as e:
            raise KeyError(f"No executor registered for domain {domain!r}") from e

    def domains(self) -> Iterator[str]:
        return iter(self._executors.keys())


executor_registry = ExecutorRegistry()
