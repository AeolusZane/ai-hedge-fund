"""Agent Registry API — CRUD for external agents + trigger execution.

Endpoints:
  POST   /api/v1/agents              Register a new agent
  GET    /api/v1/agents              List all registered agents
  GET    /api/v1/agents/{agent_id}   Get agent details
  PUT    /api/v1/agents/{agent_id}   Update agent config
  DELETE /api/v1/agents/{agent_id}   Unregister an agent
  POST   /api/v1/agents/{agent_id}/trigger   Manually trigger an agent run
  GET    /api/v1/agents/{agent_id}/runs      List recent runs
  GET    /api/v1/agents/{agent_id}/outputs   Get latest outputs
"""

import uuid
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
from app.backend.services.context_router import collect_upstream_context
from app.backend.services.agent_trigger import trigger_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents")


# ── Request / Response schemas ──────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    endpoint: str
    schedule: Optional[str] = None
    input_keys: Optional[list[str]] = None
    output_keys: Optional[list[str]] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class AgentUpdate(BaseModel):
    description: Optional[str] = None
    endpoint: Optional[str] = None
    schedule: Optional[str] = None
    input_keys: Optional[list[str]] = None
    output_keys: Optional[list[str]] = None
    is_active: Optional[bool] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class AgentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    endpoint: str
    schedule: Optional[str]
    is_active: bool
    input_keys: Optional[list[str]]
    output_keys: Optional[list[str]]
    color: Optional[str]
    icon: Optional[str]
    last_run_at: Optional[datetime]
    last_run_status: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TriggerRequest(BaseModel):
    """Optional config to pass to the agent on this run."""
    config: Optional[dict] = None
    trigger_type: str = "manual"


class RunResponse(BaseModel):
    id: int
    run_id: str
    agent_name: str
    status: str
    progress: Optional[int]
    message: Optional[str]
    metrics: Optional[dict]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    trigger_type: str
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── CRUD ────────────────────────────────────────────────────────────

@router.post("", response_model=AgentResponse, status_code=201)
def register_agent(body: AgentCreate, db: Session = Depends(get_db)):
    """Register a new external agent."""
    existing = db.query(RegisteredAgent).filter(RegisteredAgent.name == body.name).first()
    if existing:
        raise HTTPException(400, f"Agent '{body.name}' already registered")

    agent = RegisteredAgent(
        name=body.name,
        description=body.description,
        endpoint=body.endpoint,
        schedule=body.schedule,
        input_keys=body.input_keys,
        output_keys=body.output_keys,
        color=body.color,
        icon=body.icon,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    logger.info(f"Registered agent: {agent.name} -> {agent.endpoint}")
    return agent


@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    """List all registered agents."""
    return db.query(RegisteredAgent).order_by(RegisteredAgent.created_at.desc()).all()


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(RegisteredAgent).filter(RegisteredAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
def update_agent(agent_id: int, body: AgentUpdate, db: Session = Depends(get_db)):
    agent = db.query(RegisteredAgent).filter(RegisteredAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)

    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
def unregister_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(RegisteredAgent).filter(RegisteredAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    db.delete(agent)
    db.commit()


# ── Trigger ─────────────────────────────────────────────────────────

@router.post("/{agent_id}/trigger", response_model=RunResponse)
async def trigger_agent_run(
    agent_id: int,
    body: TriggerRequest,
    db: Session = Depends(get_db),
):
    """Manually trigger an agent run.

    1. Create an AgentRun record
    2. Collect upstream context from connected agents
    3. POST to the agent's endpoint with context + callback URL
    """
    agent = db.query(RegisteredAgent).filter(RegisteredAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    run_id = uuid.uuid4().hex[:16]

    # Create run record
    run = AgentRun(
        agent_id=agent.id,
        agent_name=agent.name,
        run_id=run_id,
        status="pending",
        trigger_type=body.trigger_type,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Collect upstream context
    context = collect_upstream_context(db, agent.id)

    # Merge user-provided config into context
    if body.config:
        context["_config"] = body.config

    # Fire and forget — the agent will call back
    await trigger_agent(agent, run_id, context)

    # Update status to running
    run.status = "running"
    db.commit()
    db.refresh(run)

    return run


# ── Run history ─────────────────────────────────────────────────────

@router.get("/{agent_id}/runs", response_model=list[RunResponse])
def list_runs(agent_id: int, limit: int = 20, db: Session = Depends(get_db)):
    agent = db.query(RegisteredAgent).filter(RegisteredAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    return (
        db.query(AgentRun)
        .filter(AgentRun.agent_id == agent_id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
        .all()
    )


# ── Outputs ─────────────────────────────────────────────────────────

@router.get("/{agent_id}/outputs")
def get_latest_outputs(agent_id: int, db: Session = Depends(get_db)):
    """Get the latest output data from this agent."""
    agent = db.query(RegisteredAgent).filter(RegisteredAgent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    # Get the most recent successful run
    latest_run = (
        db.query(AgentRun)
        .filter(AgentRun.agent_id == agent_id, AgentRun.status == "success")
        .order_by(AgentRun.completed_at.desc())
        .first()
    )
    if not latest_run:
        return {"outputs": []}

    outputs = (
        db.query(AgentOutput)
        .filter(AgentOutput.run_id == latest_run.run_id)
        .all()
    )

    return {
        "run_id": latest_run.run_id,
        "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
        "outputs": [
            {
                "key": o.output_key,
                "data": o.data,
                "created_at": o.created_at.isoformat(),
            }
            for o in outputs
        ],
    }


# ── Connections ─────────────────────────────────────────────────────

class ConnectionCreate(BaseModel):
    source_agent_id: int
    source_output_key: Optional[str] = None
    target_agent_id: int
    target_input_key: Optional[str] = None
    flow_id: Optional[int] = None


@router.post("/connections", status_code=201)
def create_connection(body: ConnectionCreate, db: Session = Depends(get_db)):
    """Create a connection between two agents."""
    conn = AgentConnection(
        source_agent_id=body.source_agent_id,
        source_output_key=body.source_output_key,
        target_agent_id=body.target_agent_id,
        target_input_key=body.target_input_key,
        flow_id=body.flow_id,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return {"id": conn.id, "message": "Connection created"}


@router.get("/connections")
def list_connections(flow_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List all connections, optionally filtered by flow."""
    q = db.query(AgentConnection)
    if flow_id is not None:
        q = q.filter(AgentConnection.flow_id == flow_id)
    conns = q.all()
    return [
        {
            "id": c.id,
            "source_agent_id": c.source_agent_id,
            "source_output_key": c.source_output_key,
            "target_agent_id": c.target_agent_id,
            "target_input_key": c.target_input_key,
            "flow_id": c.flow_id,
        }
        for c in conns
    ]


@router.delete("/connections/{conn_id}", status_code=204)
def delete_connection(conn_id: int, db: Session = Depends(get_db)):
    conn = db.query(AgentConnection).filter(AgentConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Connection not found")
    db.delete(conn)
    db.commit()
