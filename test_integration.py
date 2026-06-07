"""Integration test for bug-fix workflow with mocked external services."""
import asyncio
import json
import sys
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.backend.domains.bug_fix.executor import BugFixExecutor
from app.backend.core.executors.base import ProgressEvent


async def test_bug_fix_workflow():
    """Test the complete bug-fix workflow with mocked external services."""
    
    print("=" * 60)
    print("Bug Fix Workflow Integration Test")
    print("=" * 60)
    
    # Mock data
    mock_jira_detail = {
        "key": "TEST-001",
        "summary": "Test bug: NullPointerException in UserService",
        "description": "When calling getUserById with null ID, the service throws NPE",
        "status": "Open",
        "priority": "High",
        "reporter": "test.user@example.com",
    }
    
    mock_analysis = {
        "root_cause": "Missing null check in UserService.getUserById()",
        "bug_type": "null_pointer",
        "severity": "medium",
        "affected_files": ["src/main/java/com/example/UserService.java"],
        "patch_strategy": "Add null check before accessing user object",
        "confidence": 0.85,
    }
    
    mock_patch = {
        "diff": """--- a/src/main/java/com/example/UserService.java
+++ b/src/main/java/com/example/UserService.java
@@ -42,6 +42,9 @@ public class UserService {
     }
     
     public User getUserById(String id) {
+        if (id == null) {
+            throw new IllegalArgumentException("User ID cannot be null");
+        }
         return userRepository.findById(id);
     }
 }""",
        "files_changed": ["src/main/java/com/example/UserService.java"],
        "patch_confidence": 0.9,
    }
    
    mock_test_result = {
        "test_passed": True,
        "test_output": "All 15 tests passed",
        "coverage_delta": 0.0,
    }
    
    mock_pr_result = {
        "pr_url": "https://code.fineres.com/projects/AI/repos/corevo/pull-requests/123",
        "pr_id": 123,
        "branch": "bugfix/TEST-001-null-check",
    }
    
    # Create executor
    executor = BugFixExecutor()
    
    # Mock external services
    with patch('app.backend.domains.bug_fix.executor.fetch_jira_detail', new_callable=AsyncMock) as mock_jira, \
         patch('app.backend.domains.bug_fix.executor.clone_repo', new_callable=AsyncMock) as mock_clone, \
         patch('app.backend.domains.bug_fix.executor.run_analyze', new_callable=AsyncMock) as mock_analyze, \
         patch('app.backend.domains.bug_fix.executor.run_patch', new_callable=AsyncMock) as mock_patch_fn, \
         patch('app.backend.domains.bug_fix.executor.run_test', new_callable=AsyncMock) as mock_test, \
         patch('app.backend.domains.bug_fix.executor.create_pull_request', new_callable=AsyncMock) as mock_pr, \
         patch('app.backend.domains.bug_fix.executor.post_feedback_template', new_callable=AsyncMock) as mock_feedback:
        
        # Configure mocks
        mock_jira.return_value = mock_jira_detail
        mock_clone.return_value = "/tmp/mock-repo"
        mock_analyze.return_value = mock_analysis
        mock_patch_fn.return_value = mock_patch
        mock_test.return_value = mock_test_result
        mock_pr.return_value = mock_pr_result
        mock_feedback.return_value = True
        
        # Progress callback
        events = []
        async def on_progress(event: ProgressEvent):
            events.append(event)
            print(f"\n[{event.node_id}] {event.status.value}")
            if event.payload:
                for key, value in event.payload.items():
                    if isinstance(value, str) and len(value) > 100:
                        value = value[:100] + "..."
                    print(f"  {key}: {value}")
        
        # Run workflow
        print("\nExecuting workflow...")
        request_data = {
            "jira_issue": "TEST-001",
            "project_key": "TEST",
            "repo_name": "corevo",
        }
        
        try:
            result = await executor.execute(
                request_data=request_data,
                on_progress=on_progress,
                api_keys={},
            )
            
            print("\n" + "=" * 60)
            print("Workflow completed successfully!")
            print("=" * 60)
            print(f"\nResult keys: {list(result.keys())}")
            print(f"PR URL: {result.get('pr_url', 'N/A')}")
            print(f"Experience ID: {result.get('experience_id', 'N/A')}")
            
            # Verify mocks were called
            print("\n" + "=" * 60)
            print("Mock verification:")
            print("=" * 60)
            print(f"✓ Jira fetch called: {mock_jira.called}")
            print(f"✓ Repo clone called: {mock_clone.called}")
            print(f"✓ Analyze called: {mock_analyze.called}")
            print(f"✓ Patch called: {mock_patch_fn.called}")
            print(f"✓ Test called: {mock_test.called}")
            print(f"✓ PR creation called: {mock_pr.called}")
            print(f"✓ Feedback template called: {mock_feedback.called}")
            
            print("\n" + "=" * 60)
            print("TEST PASSED")
            print("=" * 60)
            return True
            
        except Exception as e:
            print(f"\n❌ Workflow failed: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(test_bug_fix_workflow())
    sys.exit(0 if success else 1)
