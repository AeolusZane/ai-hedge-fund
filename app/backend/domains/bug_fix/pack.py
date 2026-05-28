"""Side-effect module that registers the bug-fix stub executor."""
from app.backend.core.executors import executor_registry
from app.backend.domains.bug_fix.executor import BugFixExecutor

executor_registry.register(BugFixExecutor())
