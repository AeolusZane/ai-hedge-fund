"""Agent Trigger — call external agent endpoints.

When the platform triggers an agent, it:
1. POSTs to the agent's endpoint with context + callback URL
2. The agent runs externally and calls back to report status/output

This is fire-and-forget — the platform doesn't wait for the agent to finish.
"""

import logging
import httpx
from typing import Optional

from app.backend.database.agent_models import RegisteredAgent

logger = logging.getLogger(__name__)

# Base URL for callbacks (agents will POST back here)
# In production, this should be configurable via environment variable
CALLBACK_BASE_URL = "http://localhost:8000"


async def trigger_agent(
    agent: RegisteredAgent,
    run_id: str,
    context: dict,
    callback_base_url: Optional[str] = None,
) -> bool:
    """Trigger an external agent by POSTing to its endpoint.

    Args:
        agent: The registered agent to trigger
        run_id: Unique identifier for this run
        context: Upstream data to inject as context
        callback_base_url: Base URL for callbacks (defaults to localhost)

    Returns:
        True if the request was sent successfully, False otherwise
    """
    base_url = callback_base_url or CALLBACK_BASE_URL

    # Build the callback URLs
    status_callback = f"{base_url}/api/v1/callback/{run_id}/status"
    output_callback = f"{base_url}/api/v1/callback/{run_id}/output"

    # Build the request payload
    payload = {
        "run_id": run_id,
        "context": context,
        "callbacks": {
            "status": status_callback,
            "output": output_callback,
        },
    }

    logger.info(f"Triggering agent {agent.name} at {agent.endpoint} (run_id={run_id})")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(agent.endpoint, json=payload)
            response.raise_for_status()
            logger.info(f"Agent {agent.name} triggered successfully")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to trigger agent {agent.name}: {e}")
        return False


def trigger_agent_async(
    agent: RegisteredAgent,
    run_id: str,
    context: dict,
    callback_base_url: Optional[str] = None,
):
    """Fire-and-forget trigger (for downstream agents).

    This is called from the callback handler when an upstream agent completes.
    We don't await it — the agent will call back when it's done.
    """
    import asyncio

    # Schedule the trigger as a background task
    asyncio.create_task(
        trigger_agent(agent, run_id, context, callback_base_url)
    )
