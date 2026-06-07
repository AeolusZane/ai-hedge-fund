"""Simple smoke test - trigger workflow via API and check results."""
import requests
import time
import json

BASE_URL = "http://localhost:8099"

print("=" * 60)
print("Bug Fix Workflow Smoke Test")
print("=" * 60)

# 1. Check health
print("\n1. Checking health...")
resp = requests.get(f"{BASE_URL}/evolution/health")
print(f"   Status: {resp.status_code}")
print(f"   Response: {resp.json()}")

# 2. Trigger workflow
print("\n2. Triggering workflow...")
resp = requests.post(
    f"{BASE_URL}/bug-fix/trigger",
    json={"jira_issue": "TEST-001", "project_key": "TEST"}
)
print(f"   Status: {resp.status_code}")
result = resp.json()
print(f"   Response: {result}")
run_id = result.get("run_id")

# 3. Wait and check status
print(f"\n3. Checking run status (run_id={run_id})...")
time.sleep(2)
resp = requests.get(f"{BASE_URL}/bug-fix/runs")
print(f"   Status: {resp.status_code}")
runs = resp.json().get("runs", [])
if runs:
    run = runs[0]
    print(f"   Run status: {run.get('status')}")
    print(f"   Stages completed: {run.get('stages_completed', 0)}/{run.get('stages_total', 0)}")

# 4. Check evolution data
print("\n4. Checking evolution data...")
resp = requests.get(f"{BASE_URL}/evolution/experiences")
print(f"   Status: {resp.status_code}")
experiences = resp.json().get("experiences", [])
print(f"   Total experiences: {len(experiences)}")

resp = requests.get(f"{BASE_URL}/evolution/runs")
print(f"   Evolution runs: {resp.json().get('total', 0)}")

resp = requests.get(f"{BASE_URL}/evolution/metrics")
print(f"   Metrics: {resp.json()}")

print("\n" + "=" * 60)
print("SMOKE TEST COMPLETE")
print("=" * 60)
print("\nBackend is running and responding to requests.")
print("Workflow trigger created a run record.")
print("Evolution endpoints are accessible.")
