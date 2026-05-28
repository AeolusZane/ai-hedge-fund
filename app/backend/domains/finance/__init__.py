"""Finance domain pack.

Importing this package registers the FinanceExecutor with the platform
executor registry. The pack itself remains a thin shim today — most code
still lives under `src/` and `app/backend/services/`; later phases will
relocate those files here.
"""
from app.backend.core.executors import executor_registry
from app.backend.domains.finance.executor import FinanceExecutor

executor_registry.register(FinanceExecutor())
