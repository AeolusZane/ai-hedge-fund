"""Database models for the Agent Platform.

The platform is a scheduler + monitor + data router for external agents.
Agents run externally and report back via callback APIs.

Two data channels:
  1. Agent → Platform: status reports (fixed format, for monitoring)
  2. Agent → Platform: output data (opaque JSON, for downstream agents)
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON, Float, ForeignKey
from sqlalchemy.sql import func
from .connection import Base


class RegisteredAgent(Base):
    """An external agent registered with the platform.

    The platform knows:
      - where to reach it (endpoint)
      - when to trigger it (schedule)
      - what it outputs (output_keys, just names, no schema)
      - what it needs (input_keys, just names, no schema)
    """
    __tablename__ = "registered_agents"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Identity
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)

    # Where to reach it
    endpoint = Column(String(500), nullable=False)  # e.g. https://arxiv-agent.com/run

    # When to trigger (cron expression, optional)
    schedule = Column(String(100), nullable=True)  # e.g. "0 */6 * * *"
    is_active = Column(Boolean, default=True)

    # I/O declaration (just names, no schema enforcement)
    input_keys = Column(JSON, nullable=True)   # e.g. ["config", "papers"]
    output_keys = Column(JSON, nullable=True)  # e.g. ["papers", "metadata"]

    # Display
    color = Column(String(20), nullable=True)  # hex color for canvas node
    icon = Column(String(50), nullable=True)   # icon name

    # Last known state (denormalized for quick reads)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String(20), nullable=True)  # success / failed / running


class AgentRun(Base):
    """A single execution of an agent.

    Created when the platform triggers an agent.
    Updated as the agent reports status and output.
    """
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Who
    agent_id = Column(Integer, ForeignKey("registered_agents.id"), nullable=False, index=True)
    agent_name = Column(String(200), nullable=False)  # denormalized for quick reads

    # Unique run identifier (used in callback URLs)
    run_id = Column(String(64), nullable=False, unique=True, index=True)

    # Status tracking (channel 1: monitoring)
    status = Column(String(20), nullable=False, default="pending")
    # pending → running → success / failed / timeout
    progress = Column(Integer, nullable=True)  # 0-100
    message = Column(Text, nullable=True)      # human-readable status message
    metrics = Column(JSON, nullable=True)      # optional numeric metrics

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Trigger info
    trigger_type = Column(String(20), nullable=False, default="manual")
    # manual / scheduled / upstream (triggered by another agent's output)

    # Error info
    error_message = Column(Text, nullable=True)


class AgentOutput(Base):
    """Opaque output data from an agent run.

    The platform stores this without understanding its structure.
    When a downstream agent is triggered, the platform collects
    upstream outputs and injects them as context.
    """
    __tablename__ = "agent_outputs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Which run produced this
    run_id = Column(String(64), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("registered_agents.id"), nullable=False, index=True)
    agent_name = Column(String(200), nullable=False)

    # The output data (opaque JSON — platform doesn't parse this)
    data = Column(JSON, nullable=False)

    # Optional: which output key this belongs to
    # e.g. if agent outputs {"papers": [...], "metadata": {...}}
    # there would be two rows: one with key="papers", one with key="metadata"
    output_key = Column(String(100), nullable=True)


class AgentConnection(Base):
    """Edges between agents on the canvas.

    Defines the data flow graph: when agent A finishes,
    its output is available as context for agent B.
    """
    __tablename__ = "agent_connections"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Source agent (upstream)
    source_agent_id = Column(Integer, ForeignKey("registered_agents.id"), nullable=False, index=True)
    source_output_key = Column(String(100), nullable=True)  # which output to pass (optional)

    # Target agent (downstream)
    target_agent_id = Column(Integer, ForeignKey("registered_agents.id"), nullable=False, index=True)
    target_input_key = Column(String(100), nullable=True)  # what name to use in context

    # Which flow/canvas this connection belongs to
    flow_id = Column(Integer, ForeignKey("hedge_fund_flows.id"), nullable=True, index=True)
