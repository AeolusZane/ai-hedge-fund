"""Agent SDK — Template for external agent developers.

This is a minimal FastAPI app that:
1. Receives trigger requests from the platform
2. Reports status updates back to the platform
3. Reports output data back to the platform

Usage:
    1. Copy this file to your agent project
    2. Implement your logic in the `run_agent` function
    3. Run with: uvicorn agent_sdk:app --host 0.0.0.0 --port 8001
    4. Register your agent with the platform:
       POST /api/v1/agents
       {
         "name": "my-agent",
         "endpoint": "http://your-server:8001/run",
         "schedule": "0 */6 * * *",  // optional cron
         "input_keys": ["config"],
         "output_keys": ["results"]
       }
"""

import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI()


# ── Request/Response schemas ────────────────────────────────────────

class TriggerRequest(BaseModel):
    """Request from the platform to trigger this agent."""
    run_id: str
    context: dict  # upstream data from connected agents
    callbacks: dict  # URLs to report status and output


class StatusReport(BaseModel):
    """Status update to send back to the platform."""
    status: str  # running / success / failed
    progress: Optional[int] = None  # 0-100
    message: Optional[str] = None
    metrics: Optional[dict] = None
    error_message: Optional[str] = None


class OutputReport(BaseModel):
    """Output data to send back to the platform."""
    data: dict  # your agent's output (any JSON)
    output_key: Optional[str] = None  # e.g. "papers", "results"


# ── Callback helpers ────────────────────────────────────────────────

async def report_status(callbacks: dict, status: StatusReport):
    """Report status update to the platform."""
    async with httpx.AsyncClient() as client:
        await client.post(callbacks["status"], json=status.model_dump())


async def report_output(callbacks: dict, output: OutputReport):
    """Report output data to the platform."""
    async with httpx.AsyncClient() as client:
        await client.post(callbacks["output"], json=output.model_dump())


# ── Your agent logic ────────────────────────────────────────────────

async def run_agent(run_id: str, context: dict, callbacks: dict):
    """Implement your agent logic here.

    Args:
        run_id: Unique identifier for this run
        context: Upstream data from connected agents
        callbacks: URLs to report status and output

    Example:
        # Report progress
        await report_status(callbacks, StatusReport(
            status="running",
            progress=50,
            message="Processing data..."
        ))

        # Do your work
        results = await process_data(context)

        # Report output
        await report_output(callbacks, OutputReport(
            data={"results": results},
            output_key="results"
        ))

        # Report success
        await report_status(callbacks, StatusReport(
            status="success",
            progress=100,
            message="Completed successfully",
            metrics={"items_processed": len(results)}
        ))
    """
    # Report that we're starting
    await report_status(callbacks, StatusReport(
        status="running",
        progress=0,
        message="Starting..."
    ))

    try:
        # ── YOUR LOGIC HERE ──────────────────────────────────────
        # Access upstream data via context dict
        # e.g. papers = context.get("arxiv-collector", {}).get("papers", [])

        # Example: just echo back the context
        output_data = {
            "received_context": context,
            "message": "This is a template. Implement your logic here."
        }

        # Report progress
        await report_status(callbacks, StatusReport(
            status="running",
            progress=50,
            message="Processing..."
        ))

        # Report output
        await report_output(callbacks, OutputReport(
            data=output_data,
            output_key="results"
        ))

        # Report success
        await report_status(callbacks, StatusReport(
            status="success",
            progress=100,
            message="Completed successfully",
            metrics={"items_processed": 1}
        ))

    except Exception as e:
        # Report failure
        await report_status(callbacks, StatusReport(
            status="failed",
            error_message=str(e)
        ))


# ── FastAPI endpoint ────────────────────────────────────────────────

@app.post("/run")
async def trigger(request: TriggerRequest):
    """Endpoint called by the platform to trigger this agent.

    This should return immediately — the actual work happens in the background.
    """
    # Run the agent in the background
    import asyncio
    asyncio.create_task(run_agent(request.run_id, request.context, request.callbacks))

    return {"status": "accepted", "run_id": request.run_id}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# ── Example: arXiv paper collector ──────────────────────────────────

"""
Example implementation for an arXiv collector agent:

async def run_agent(run_id: str, context: dict, callbacks: dict):
    await report_status(callbacks, StatusReport(
        status="running",
        progress=0,
        message="Fetching papers from arXiv..."
    ))

    try:
        # Get config from context (if provided)
        config = context.get("_config", {})
        keywords = config.get("keywords", ["LLM", "agent"])

        # Fetch papers from arXiv API
        papers = []
        for i, keyword in enumerate(keywords):
            await report_status(callbacks, StatusReport(
                status="running",
                progress=int((i / len(keywords)) * 80),
                message=f"Searching for '{keyword}'..."
            ))

            # Call arXiv API
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://export.arxiv.org/api/query",
                    params={"search_query": f"all:{keyword}", "max_results": 10}
                )
                # Parse response and add to papers list
                papers.extend(parse_arxiv_response(response.text, keyword))

        # Report output
        await report_output(callbacks, OutputReport(
            data={"papers": papers},
            output_key="papers"
        ))

        # Report success
        await report_status(callbacks, StatusReport(
            status="success",
            progress=100,
            message=f"Collected {len(papers)} papers",
            metrics={"papers_collected": len(papers), "keywords_searched": len(keywords)}
        ))

    except Exception as e:
        await report_status(callbacks, StatusReport(
            status="failed",
            error_message=str(e)
        ))
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
