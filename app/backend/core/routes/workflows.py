"""Generic domain run endpoint.

POST /workflows/{domain}/run resolves a WorkflowExecutor from the registry,
streams its ProgressEvents as SSE, and persists a FlowRun row when the
caller supplies `flow_id`. Domain-specific routes (e.g. /hedge-fund/run)
remain available for backwards compatibility.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backend.core.executors import ExecutorContext, ProgressEvent, executor_registry
from app.backend.database import get_db
from app.backend.models.events import CompleteEvent, ErrorEvent, ProgressUpdateEvent, StartEvent
from app.backend.models.schemas import FlowRunStatus
from app.backend.repositories.flow_run_repository import FlowRunRepository
from app.backend.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowRunRequest(BaseModel):
    """Wrapper for generic workflow runs.

    `payload` is forwarded verbatim to the executor — its shape is
    domain-specific. The top-level fields (`flow_id`, `api_keys`) are
    consumed by the platform itself.
    """

    payload: dict[str, Any] = {}
    flow_id: Optional[int] = None
    api_keys: Optional[dict[str, str]] = None


@router.get("/domains")
async def list_domains() -> dict[str, list[str]]:
    """List the executor ids currently registered."""
    return {"domains": list(executor_registry.domains())}


@router.post("/{domain}/run")
async def run(
    domain: str,
    request_data: WorkflowRunRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        executor = executor_registry.get(domain)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown domain {domain!r}")

    api_keys = request_data.api_keys
    if not api_keys:
        api_keys = ApiKeyService(db).get_api_keys_dict()

    flow_run_repo = FlowRunRepository(db)
    flow_run = None
    if request_data.flow_id is not None:
        flow_run = flow_run_repo.create_flow_run(
            flow_id=request_data.flow_id,
            request_data={"domain": domain, "payload": request_data.payload},
        )
        flow_run_repo.update_flow_run(flow_run.id, status=FlowRunStatus.IN_PROGRESS)

    async def wait_for_disconnect() -> bool:
        try:
            while True:
                message = await request.receive()
                if message["type"] == "http.disconnect":
                    return True
        except Exception:
            return True

    async def event_generator():
        progress_queue: asyncio.Queue = asyncio.Queue()
        run_task = None
        disconnect_task = None
        cancelled = {"value": False}

        def emit(event: ProgressEvent) -> None:
            payload = event.payload or {}
            progress_queue.put_nowait(
                ProgressUpdateEvent(
                    agent=event.node_id,
                    ticker=payload.get("ticker"),
                    status=event.status,
                    timestamp=payload.get("timestamp"),
                    analysis=payload.get("analysis"),
                    chunk=payload.get("chunk"),
                )
            )

        context = ExecutorContext(
            db=db,
            api_keys=api_keys or {},
            emit=emit,
            is_cancelled=lambda: cancelled["value"],
        )

        try:
            run_task = asyncio.create_task(executor.run(request_data.payload, context))
            disconnect_task = asyncio.create_task(wait_for_disconnect())

            yield StartEvent().to_sse()

            while not run_task.done():
                if disconnect_task.done():
                    cancelled["value"] = True
                    run_task.cancel()
                    try:
                        await run_task
                    except asyncio.CancelledError:
                        pass
                    return

                try:
                    event = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    pass

            try:
                final_payload = await run_task
            except asyncio.CancelledError:
                return

            if flow_run:
                # Check if any stage recorded an error
                has_error = any(
                    key.endswith("_error") and final_payload.get(key)
                    for key in final_payload
                )
                if has_error:
                    error_messages = [
                        f"{k}: {v}" for k, v in final_payload.items()
                        if k.endswith("_error") and v
                    ]
                    flow_run_repo.update_flow_run(
                        flow_run.id,
                        status=FlowRunStatus.ERROR,
                        error_message="; ".join(error_messages),
                        results=final_payload,
                    )
                else:
                    flow_run_repo.update_flow_run(
                        flow_run.id, status=FlowRunStatus.COMPLETE, results=final_payload
                    )
            yield CompleteEvent(data=final_payload).to_sse()

        except asyncio.CancelledError:
            if flow_run:
                flow_run_repo.update_flow_run(
                    flow_run.id,
                    status=FlowRunStatus.ERROR,
                    error_message="Run cancelled by client",
                )
            return
        except Exception as exc:
            if flow_run:
                flow_run_repo.update_flow_run(
                    flow_run.id, status=FlowRunStatus.ERROR, error_message=str(exc)
                )
            yield ErrorEvent(message=str(exc)).to_sse()
            return
        finally:
            if run_task and not run_task.done():
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
            if disconnect_task and not disconnect_task.done():
                disconnect_task.cancel()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
