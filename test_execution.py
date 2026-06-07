"""Test workflow execution with mocked external services."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from app.backend.domains.bug_fix.executor import BugFixExecutor
from app.backend.core.executors.base import ExecutorContext, ProgressEvent


async def test_execution():
    """Test the executor with graph_nodes providing proper node_data."""
    
    print("=" * 60)
    print("Testing Workflow Execution (Mocked)")
    print("=" * 60)
    
    executor = BugFixExecutor()
    
    # Mock data
    mock_jira = {
        "key": "TEST-001",
        "summary": "NullPointerException in UserService",
        "description": "NPE when calling getUserById with null",
        "status": "Open",
        "priority": "High",
    }
    
    mock_analysis = {
        "root_cause_hypothesis": "Missing null check in getUserById()",
        "bug_type": "null_pointer",
        "severity": "medium",
        "affected_files": ["UserService.java"],
        "patch_strategy": "Add null check before accessing user object",
        "confidence": 0.85,
        "decision_steps": [],
    }
    
    mock_patch = {
        "diff": "--- a/UserService.java\n+++ b/UserService.java\n@@ -1 +1,3 @@\n+if (id == null) return null;",
        "files_changed": ["UserService.java"],
        "status": "applied",
    }
    
    mock_pr = {
        "pr_url": "https://bitbucket.org/projects/AI/repos/corevo/pull-requests/123",
        "pr_id": 123,
        "branch": "bugfix/TEST-001",
    }
    
    # Create mock context — emit is sync (not async) based on executor usage
    events = []
    def mock_emit(event: ProgressEvent):
        events.append(event)
        status_val = event.status if isinstance(event.status, str) else event.status.value
        status_icon = "✓" if status_val == "Done" else "⏳" if "analyzing" in status_val.lower() else "○"
        print(f"  {status_icon} [{event.node_id}] {status_val}")
    
    context = ExecutorContext(
        db=MagicMock(),
        api_keys={},
        emit=mock_emit,
        is_cancelled=lambda: False,
        run_id=1,
    )
    
    # Provide graph_nodes with proper node_data (repoUrl is required by Patch and Open PR)
    graph_nodes = [
        {
            "id": "jira",
            "type": "jira-issue-input-node",
            "position": {"x": 0, "y": 0},
            "data": {"componentName": "Jira Issue Input"},
        },
        {
            "id": "analyze",
            "type": "bug-fix-stage-node",
            "position": {"x": 320, "y": 0},
            "data": {
                "componentName": "Analyze",
                "name": "Analyze",
                "repoUrl": "https://code.fineres.com/projects/AI/repos/corevo",
                "targetBranch": "main",
            },
        },
        {
            "id": "patch",
            "type": "bug-fix-stage-node",
            "position": {"x": 640, "y": 0},
            "data": {
                "componentName": "Patch",
                "name": "Patch",
                "repoUrl": "https://code.fineres.com/projects/AI/repos/corevo",
                "targetBranch": "main",
            },
        },
        {
            "id": "test",
            "type": "bug-fix-stage-node",
            "position": {"x": 960, "y": 0},
            "data": {"componentName": "Test", "name": "Test"},
        },
        {
            "id": "open_pr",
            "type": "bug-fix-stage-node",
            "position": {"x": 1280, "y": 0},
            "data": {
                "componentName": "Open PR",
                "name": "Open PR",
                "repoUrl": "https://code.fineres.com/projects/AI/repos/corevo",
                "project": "AI",
                "repo": "corevo",
            },
        },
    ]
    
    graph_edges = [
        {"id": "jira-analyze", "source": "jira", "target": "analyze"},
        {"id": "analyze-patch", "source": "analyze", "target": "patch"},
        {"id": "patch-test", "source": "patch", "target": "test"},
        {"id": "test-open_pr", "source": "test", "target": "open_pr"},
    ]
    
    # Patch external functions
    with patch('app.backend.domains.bug_fix.executor.get_issue_detail', new_callable=AsyncMock) as m_jira, \
         patch('app.backend.domains.bug_fix.executor.clone_repo', new_callable=AsyncMock) as m_clone, \
         patch('app.backend.domains.bug_fix.executor.analyze_jira_issue', new_callable=AsyncMock) as m_analyze, \
         patch('app.backend.domains.bug_fix.executor.run_patch', new_callable=AsyncMock) as m_patch, \
         patch('app.backend.domains.bug_fix.executor.open_pr', new_callable=AsyncMock) as m_pr, \
         patch.object(BugFixExecutor, '_commit_and_push', new_callable=AsyncMock) as m_commit:
        
        # Create a real temp git repo so git operations work
        import tempfile
        import subprocess
        tmpdir = tempfile.mkdtemp(prefix="mock-repo-")
        subprocess.run(["git", "init", tmpdir], check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", "https://code.fineres.com/projects/AI/repos/corevo"], 
                      cwd=tmpdir, check=True, capture_output=True)
        # Create a dummy file so there's something to commit
        Path(tmpdir, "UserService.java").write_text("public class UserService {}")
        subprocess.run(["git", "add", "."], cwd=tmpdir, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.email=test@test.com", "-c", "user.name=test", 
                       "commit", "-m", "init"], cwd=tmpdir, check=True, capture_output=True)
        
        m_jira.return_value = mock_jira
        m_clone.return_value = Path(tmpdir)
        m_analyze.return_value = mock_analysis
        m_patch.return_value = mock_patch
        m_pr.return_value = mock_pr
        m_commit.return_value = None  # _commit_and_push returns nothing on success
        
        # Execute
        print("\nExecuting workflow...")
        request = {
            "jira_issue": "TEST-001",
            "project_key": "TEST",
            "stage_delay_seconds": 0.01,
            "graph_nodes": graph_nodes,
            "graph_edges": graph_edges,
        }
        
        try:
            result = await executor.run(request, context)
            
            print("\n" + "=" * 60)
            print("EXECUTION RESULT")
            print("=" * 60)
            
            # Check results
            ok = True
            checks = [
                ("jira_issue", result.get("jira_issue"), "TEST-001"),
                ("branch", result.get("branch"), None),
                ("analysis present", "analysis" in result, True),
                ("patch present", "patch" in result, True),
                ("open_pr present", "open_pr" in result, True),
                ("stages_executed", len(result.get("stages_executed", [])), 5),
            ]
            
            for name, actual, expected in checks:
                if expected is not None:
                    passed = actual == expected
                else:
                    passed = actual is not None
                icon = "✓" if passed else "✗"
                if not passed:
                    ok = False
                print(f"  {icon} {name}: {actual}" + (f" (expected {expected})" if expected is not None and not passed else ""))
            
            # Check for errors
            for err_key in ("analyze_error", "patch_error", "open_pr_error"):
                if result.get(err_key):
                    print(f"  ✗ {err_key}: {result[err_key]}")
                    ok = False
            
            # Check mock calls
            print("\nMock call counts:")
            print(f"  Jira fetch: {m_jira.call_count}")
            print(f"  Repo clone: {m_clone.call_count}")
            print(f"  Analyze: {m_analyze.call_count}")
            print(f"  Patch: {m_patch.call_count}")
            print(f"  Commit/push: {m_commit.call_count}")
            print(f"  PR creation: {m_pr.call_count}")
            
            if ok:
                print("\n" + "=" * 60)
                print("ALL CHECKS PASSED")
                print("=" * 60)
            else:
                print("\n" + "=" * 60)
                print("SOME CHECKS FAILED")
                print("=" * 60)
            
            return ok
            
        except Exception as e:
            print(f"\nEXECUTION FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_execution())
    sys.exit(0 if success else 1)
