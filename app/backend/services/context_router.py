"""Context Router — collect upstream outputs for downstream agents.

When an agent is triggered, the platform collects the latest outputs
from all upstream agents (based on connections) and injects them
as context in the trigger request.

The platform doesn't understand the data — it just routes it.
"""

import logging
from sqlalchemy.orm import Session

from app.backend.database.agent_models import (
    AgentConnection, AgentRun, AgentOutput,
)

logger = logging.getLogger(__name__)


def collect_upstream_context(db: Session, target_agent_id: int) -> dict:
    """Collect outputs from all upstream agents connected to this target.

    Returns a dict like:
    {
        "arxiv-collector": {
            "papers": [...],
            "metadata": {...}
        },
        "xiaohongshu-collector": {
            "posts": [...]
        }
    }

    The platform doesn't parse or validate the data — it just passes it through.
    """
    # Find all connections where this agent is the target
    connections = (
        db.query(AgentConnection)
        .filter(AgentConnection.target_agent_id == target_agent_id)
        .all()
    )

    if not connections:
        return {}

    context = {}

    for conn in connections:
        # Get the latest successful run from the source agent
        latest_run = (
            db.query(AgentRun)
            .filter(
                AgentRun.agent_id == conn.source_agent_id,
                AgentRun.status == "success",
            )
            .order_by(AgentRun.completed_at.desc())
            .first()
        )

        if not latest_run:
            logger.warning(
                f"No successful run found for source agent {conn.source_agent_id}"
            )
            continue

        # Get outputs from that run
        outputs = (
            db.query(AgentOutput)
            .filter(AgentOutput.run_id == latest_run.run_id)
            .all()
        )

        if not outputs:
            logger.warning(
                f"No outputs found for run {latest_run.run_id} (agent {conn.source_agent_id})"
            )
            continue

        # Build the context entry for this upstream agent
        # If output_key is specified in the connection, only include that key
        # Otherwise, include all outputs
        if conn.source_output_key:
            # Filter to specific output key
            matching = [o for o in outputs if o.output_key == conn.source_output_key]
            if matching:
                # Use the target_input_key as the name in context, or fall back to source agent name
                context_key = conn.target_input_key or latest_run.agent_name
                context[context_key] = matching[0].data
        else:
            # Include all outputs
            context_key = conn.target_input_key or latest_run.agent_name
            if len(outputs) == 1 and outputs[0].output_key is None:
                # Single output with no key — use the data directly
                context[context_key] = outputs[0].data
            else:
                # Multiple outputs or keyed outputs — nest them
                context[context_key] = {
                    o.output_key or "data": o.data for o in outputs
                }

    logger.info(
        f"Collected context for agent {target_agent_id}: {list(context.keys())}"
    )

    return context
