"""Callback API — agents report status and output data.

Endpoints:
  POST /api/v1/callback/{run_id}/status   Report status update
  POST /api/v1/callback/{run_id}/output   Report output data

These are called by external agents during execution.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backend.database.connection import get_db
from app.backend.database.agent_models import (
    RegisteredAgent, AgentRun, AgentOutput, AgentConnection,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/callback")


# ── Request schemas ─────────────────────────────────────────────────

class StatusReport(BaseModel):
    """Status update from an agent (channel 1: monitoring)."""
    status: str  # running / success / failed
    progress: Optional[int] = None  # 0-100
    message: Optional[str] = None
    metrics: Optional[dict] = None
    error_message: Optional[str] = None


class OutputReport(BaseModel):
    """Output data from an agent (channel 2: data for downstream)."""
    data: dict  # opaque JSON — platform doesn't parse this
    output_key: Optional[str] = None  # e.g. "papers", "metadata"


# ── Status callback ─────────────────────────────────────────────────

@router.post("/{run_id}/status")
def report_status(run_id: str, body: StatusReport, db: Session = Depends(get_db)):
    """Agent reports its execution status.

    This is the monitoring channel — platform reads this to show progress.
    """
    run = db.query(AgentRun).filter(AgentRun.run_id == run_id).first()
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    # Update run record
    run.status = body.status
    if body.progress is not None:
        run.progress = body.progress
    if body.message is not None:
        run.message = body.message
    if body.metrics is not None:
        run.metrics = body.metrics
    if body.error_message is not None:
        run.error_message = body.error_message

    # Update timing
    if body.status == "running" and not run.started_at:
        run.started_at = datetime.now(timezone.utc)
    elif body.status in ("success", "failed"):
        run.completed_at = datetime.now(timezone.utc)
        if run.started_at:
            run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

    # Update agent's last run info
    agent = db.query(RegisteredAgent).filter(RegisteredAgent.id == run.agent_id).first()
    if agent:
        agent.last_run_at = datetime.now(timezone.utc)
        agent.last_run_status = body.status

    db.commit()

    logger.info(f"Run {run_id}: status={body.status} progress={body.progress} msg={body.message}")

    # If successful, trigger downstream agents
    if body.status == "success":
        _trigger_downstream(db, run)

    return {"status": "ok"}


# ── Output callback ─────────────────────────────────────────────────

@router.post("/{run_id}/output")
def report_output(run_id: str, body: OutputReport, db: Session = Depends(get_db)):
    """Agent reports its output data.

    This is the data channel — platform stores this opaquely for downstream agents.
    """
    run = db.query(AgentRun).filter(AgentRun.run_id == run_id).first()
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    # Store output
    output = AgentOutput(
        run_id=run_id,
        agent_id=run.agent_id,
        agent_name=run.agent_name,
        data=body.data,
        output_key=body.output_key,
    )
    db.add(output)
    db.commit()

    logger.info(f"Run {run_id}: stored output key={body.output_key}")

    return {"status": "ok", "output_id": output.id}


# ── Downstream trigger ──────────────────────────────────────────────

def _trigger_downstream(db: Session, completed_run: AgentRun):
    """When an agent completes, trigger any downstream agents connected to it."""
    # Find connections where this agent is the source
    connections = (
        db.query(AgentConnection)
        .filter(AgentConnection.source_agent_id == completed_run.agent_id)
        .all()
    )

    if not connections:
        return

    logger.info(f"Run {completed_run.run_id}: triggering {len(connections)} downstream agents")

    # Import here to avoid circular dependency
    from app.backend.services.agent_trigger import trigger_agent_async
    from app.backend.services.context_router import collect_upstream_context

    for conn in connections:
        target_agent = (
            db.query(RegisteredAgent)
            .filter(RegisteredAgent.id == conn.target_agent_id)
            .first()
        )
        if not target_agent or not target_agent.is_active:
            continue

        # Create a new run for the downstream agent
        import uuid
        new_run_id = uuid.uuid4().hex[:16]
        new_run = AgentRun(
            agent_id=target_agent.id,
            agent_name=target_agent.name,
            run_id=new_run_id,
            status="pending",
            trigger_type="upstream",
            started_at=datetime.now(timezone.utc),
        )
        db.add(new_run)
        db.commit()

        # Collect context for the downstream agent
        context = collect_upstream_context(db, target_agent.id)

        # Trigger asynchronously
        trigger_agent_async(target_agent, new_run_id, context)
