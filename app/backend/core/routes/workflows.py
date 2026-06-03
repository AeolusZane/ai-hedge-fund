"""Generic domain run endpoint.

POST /workflows/{domain}/run resolves a WorkflowExecutor from the registry,
streams its ProgressEvents as SSE, and persists a FlowRun row when the
caller supplies `flow_id`. Domain-specific routes (e.g. /hedge-fund/run)
remain available for backwards compatibility.
"""
from __future__ import annotations

import asyncio
import json
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
            run_id=flow_run.id if flow_run else None,
        )

        try:
            run_task = asyncio.create_task(executor.run(request_data.payload, context))
            disconnect_task = asyncio.create_task(wait_for_disconnect())

            yield StartEvent(run_id=flow_run.id if flow_run else None).to_sse()

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


# ── Node Chat & Retry Routes ──────────────────────────────────────────────────

class NodeChatRequest(BaseModel):
    """Request for node-level Agent chat."""
    node_id: str
    node_name: str
    node_type: str
    message: str
    conversation_history: list[dict[str, str]] = []
    node_config: dict[str, Any] = {}
    error_info: Optional[str] = None
    streaming_output: Optional[str] = None
    progress_timeline: Optional[str] = None
    node_status: Optional[str] = None
    repo_path: Optional[str] = None
    model_name: Optional[str] = None
    model_provider: Optional[str] = None


class RetryNodeRequest(BaseModel):
    """Request to retry a single node."""
    flow_id: int
    run_id: int
    node_id: str
    updated_config: dict[str, Any] = {}


@router.post("/{domain}/node-chat")
async def node_chat(
    domain: str,
    request_data: NodeChatRequest,
    db: Session = Depends(get_db),
):
    """Stream Agent responses for node-level debugging."""
    from app.backend.domains.bug_fix.node_chat_agent import NodeChatRequest as AgentRequest, chat_with_node

    api_keys = ApiKeyService(db).get_api_keys_dict()

    agent_request = AgentRequest(
        node_id=request_data.node_id,
        node_name=request_data.node_name,
        node_type=request_data.node_type,
        message=request_data.message,
        conversation_history=request_data.conversation_history,
        node_config=request_data.node_config,
        error_info=request_data.error_info,
        streaming_output=request_data.streaming_output,
        progress_timeline=request_data.progress_timeline,
        node_status=request_data.node_status,
        repo_path=request_data.repo_path,
        model_name=request_data.model_name,
        model_provider=request_data.model_provider,
        api_keys=api_keys,
    )

    async def event_stream():
        try:
            async for event in chat_with_node(agent_request):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{domain}/retry-node")
async def retry_node(
    domain: str,
    request_data: RetryNodeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Retry a single node with updated configuration."""
    try:
        executor = executor_registry.get(domain)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown domain {domain!r}")

    flow_run_repo = FlowRunRepository(db)
    flow_run = flow_run_repo.get_flow_run(request_data.run_id)
    if not flow_run:
        raise HTTPException(status_code=404, detail=f"FlowRun {request_data.run_id} not found")

    api_keys = ApiKeyService(db).get_api_keys_dict()

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
            run_id=flow_run.id if flow_run else None,
        )

        # Build retry payload: restore state from previous run + apply config updates
        previous_results = flow_run.results or {}
        retry_payload = {
            **previous_results,
            "retry_node_id": request_data.node_id,
            "updated_config": request_data.updated_config,
        }

        try:
            run_task = asyncio.create_task(executor.run(retry_payload, context))
            disconnect_task = asyncio.create_task(wait_for_disconnect())

            yield StartEvent(run_id=flow_run.id if flow_run else None).to_sse()

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

            # Update flow run with retry results
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
            flow_run_repo.update_flow_run(
                flow_run.id,
                status=FlowRunStatus.ERROR,
                error_message="Retry cancelled by client",
            )
            return
        except Exception as exc:
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


# ── Workspace / Sandbox Routes ────────────────────────────────────────────────

@router.get("/{domain}/workspace/{run_id}/files")
async def list_workspace_files(
    domain: str,
    run_id: int,
    path: str = "/",
    max_depth: int = 3,
):
    """List files in a run's workspace directory.

    This is a deterministic file browser — reads directly from the filesystem,
    no LLM involved. Returns a flat list of entries with type and size.
    """
    from app.backend.core.workspace import list_files, workspace_exists

    if not workspace_exists(run_id):
        raise HTTPException(status_code=404, detail=f"Workspace for run {run_id} not found")

    result = list_files(run_id, path=path, max_depth=max_depth)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/{domain}/workspace/{run_id}/file")
async def read_workspace_file(
    domain: str,
    run_id: int,
    path: str,
):
    """Read a single file from a run's workspace.

    Returns file content as text. Max 1MB by default.
    """
    from app.backend.core.workspace import read_file, workspace_exists

    if not workspace_exists(run_id):
        raise HTTPException(status_code=404, detail=f"Workspace for run {run_id} not found")

    result = read_file(run_id, path=path)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/{domain}/workspace/{run_id}")
async def delete_workspace(
    domain: str,
    run_id: int,
):
    """Delete a run's workspace directory and all its contents."""
    from app.backend.core.workspace import cleanup_workspace, workspace_exists

    if not workspace_exists(run_id):
        raise HTTPException(status_code=404, detail=f"Workspace for run {run_id} not found")

    cleanup_workspace(run_id)
    return {"status": "deleted", "run_id": run_id}
