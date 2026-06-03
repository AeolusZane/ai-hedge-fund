"""Bug Fix Dashboard API — Jira bug listing + run history."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.backend.database import get_db
from app.backend.database.models import HedgeFundFlowRun, HedgeFundFlow
from fastapi import Depends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bug-fix", tags=["bug-fix"])


@router.get("/jira/bugs")
async def list_jira_bugs(
    project: str = Query(..., description="Jira project key"),
    status: str = Query("Open", description="Bug status filter"),
    max_results: int = Query(20, ge=1, le=100),
):
    """Fetch open bugs from Jira for the given project."""
    try:
        from app.backend.domains.bug_fix.jira_client import search_bugs, JiraMcpConfigError
        bugs = await search_bugs(project_key=project, status=status, max_results=max_results)
        return {"project": project, "status": status, "bugs": bugs}
    except JiraMcpConfigError as e:
        raise HTTPException(status_code=503, detail=f"Jira not configured: {e}")
    except Exception as e:
        logger.warning(f"Failed to fetch Jira bugs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger")
async def trigger_bug_fix(
    request: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Trigger a bug-fix workflow for the given Jira issue."""
    jira_issue = request.get("jira_issue")
    project_key = request.get("project_key", "AI")
    
    if not jira_issue:
        raise HTTPException(status_code=400, detail="jira_issue is required")

    # Find or create a bug_fix flow
    flow = db.query(HedgeFundFlow).filter(
        HedgeFundFlow.domain == "bug_fix",
        HedgeFundFlow.name == f"Bug Fix - {project_key}"
    ).first()

    if not flow:
        # Create a default flow
        from app.backend.domains.bug_fix.index import bugFixTemplate
        flow = HedgeFundFlow(
            name=f"Bug Fix - {project_key}",
            description=f"Auto-created flow for {project_key} bugs",
            domain="bug_fix",
            nodes=[
                {
                    "id": node["key"],
                    "type": "bug-fix-stage-node" if node["key"] != "jira" else "jira-issue-input-node",
                    "position": {"x": node["offsetX"], "y": node["offsetY"]},
                    "data": {"componentName": node["componentName"]},
                }
                for node in bugFixTemplate["nodes"]
            ],
            edges=[
                {"id": f"{edge['source']}-{edge['target']}", "source": edge["source"], "target": edge["target"]}
                for edge in bugFixTemplate["edges"]
            ],
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)

    # Create a flow run
    from app.backend.repositories.flow_run_repository import FlowRunRepository
    run_repo = FlowRunRepository(db)
    
    # Map project to repo name
    repo_map = {
        "AI": "corevo",
        "BUSSINESS": "nuclear-webui",
        "DATAFUSION": "data-fusion-web",
    }
    
    flow_run = run_repo.create_flow_run(
        flow_id=flow.id,
        request_data={
            "jira_issue": jira_issue,
            "project_key": project_key,
            "repo_name": repo_map.get(project_key, project_key.lower()),
        }
    )

    return {
        "run_id": flow_run.id,
        "flow_id": flow.id,
        "jira_issue": jira_issue,
        "status": "created",
    }


@router.get("/runs")
async def list_bug_fix_runs(
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List all bug-fix flow runs with their current progress."""
    # Find bug_fix flows
    flows = db.query(HedgeFundFlow).filter(HedgeFundFlow.domain == "bug_fix").all()
    bug_fix_flow_ids = [f.id for f in flows]

    if not bug_fix_flow_ids:
        return {"runs": []}

    # Query runs for those flows
    query = db.query(HedgeFundFlowRun).filter(
        HedgeFundFlowRun.flow_id.in_(bug_fix_flow_ids)
    )
    if status:
        query = query.filter(HedgeFundFlowRun.status == status)

    total = query.count()
    runs = query.order_by(desc(HedgeFundFlowRun.created_at)).offset(offset).limit(limit).all()

    results = []
    for run in runs:
        request_data = run.request_data or {}
        results_data = run.results or {}

        # Extract Jira issue key
        jira_issue = request_data.get("jira_issue", "")
        jira_detail = results_data.get("jira", {})
        summary = jira_detail.get("summary", request_data.get("description", ""))

        # Extract stages progress
        stages = results_data.get("stages_executed", [])
        stages_completed = [s.get("name", "").lower() for s in stages if isinstance(s, dict)]

        # Extract PR URL
        pr_data = results_data.get("open_pr", {})
        pr_url = pr_data.get("url", "") if isinstance(pr_data, dict) else ""

        # Current stage (last stage in progress or last completed)
        current_stage = stages[-1].get("name", "") if stages else ""

        results.append({
            "id": str(run.id),
            "jira_issue": jira_issue,
            "summary": summary,
            "status": run.status.lower(),
            "current_stage": current_stage,
            "started_at": run.started_at.isoformat() if run.started_at else run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "pr_url": pr_url,
            "stages_completed": stages_completed,
        })

    return {"total": total, "runs": results}
