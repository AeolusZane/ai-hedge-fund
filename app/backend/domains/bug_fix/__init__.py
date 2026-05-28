"""Bug-fix domain pack (stub).

Importing this package registers a placeholder executor that pretends to
walk a Jira-bug → patch → PR workflow. It exists primarily to prove the
multi-domain plumbing (registry, generic run route, frontend switcher)
end-to-end without committing to a real Jira/MCP integration yet.
"""
from app.backend.core.executors import executor_registry
from app.backend.domains.bug_fix.executor import BugFixExecutor

executor_registry.register(BugFixExecutor())
