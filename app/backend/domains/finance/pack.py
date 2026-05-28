"""Side-effect module that registers the finance executor.

Kept separate from the package `__init__` so importing any finance
submodule (`agents/`, `tools/`, ...) doesn't drag the executor — and
therefore `app.backend.models.schemas` — into the import graph. Boot
code calls `import app.backend.domains.finance.pack` explicitly.
"""
from app.backend.core.executors import executor_registry
from app.backend.domains.finance.executor import FinanceExecutor

executor_registry.register(FinanceExecutor())
