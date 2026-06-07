"""Evolution Dashboard API — track agent learning progress and human feedback."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.backend.domains.bug_fix.experience_store import ExperienceStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evolution", tags=["evolution"])

# Lazy-initialized singleton
_store: Optional[ExperienceStore] = None


def get_store() -> ExperienceStore:
    global _store
    if _store is None:
        _store = ExperienceStore()
    return _store


# ─── Request/Response Models ──────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Human rating 1-5")
    feedback: str = Field("", description="Human evaluation comments")
    difficulty: str = Field("", description="Difficulty level L1/L2/L3/L4")


class ExperienceUpdateRequest(BaseModel):
    lesson: Optional[str] = None
    lesson_tags: Optional[list[str]] = None
    difficulty_level: Optional[str] = None
    human_feedback: Optional[str] = None
    human_rating: Optional[int] = Field(None, ge=1, le=5)
    bug_type: Optional[str] = None
    patch_summary: Optional[str] = None
    patch_strategy: Optional[str] = None


# ─── Runs (Experiences) Endpoints ─────────────────────────────────────────────

@router.get("/runs")
async def list_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    difficulty: str = Query("", description="Filter by difficulty L1/L2/L3/L4"),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    reviewed_only: bool = Query(False),
    search: str = Query("", description="Search in issue_key/summary/lesson"),
):
    """List all runs (experiences) with filtering and pagination."""
    store = get_store()
    experiences, total = store.list_experiences(
        limit=limit,
        offset=offset,
        difficulty=difficulty,
        min_rating=min_rating,
        reviewed_only=reviewed_only,
        search=search,
    )
    
    runs = []
    for exp in experiences:
        runs.append({
            "id": exp.id,
            "issue_key": exp.issue_key,
            "issue_summary": exp.issue_summary,
            "bug_type": exp.bug_type,
            "difficulty_level": exp.difficulty_level,
            "first_fix_success": exp.first_fix_success,
            "iteration_count": exp.iteration_count,
            "duration_seconds": exp.duration_seconds,
            "human_rating": exp.human_rating,
            "human_feedback": exp.human_feedback,
            "reviewed_at": exp.reviewed_at,
            "created_at": exp.created_at,
            "lesson": exp.lesson,
            "lesson_tags": exp.lesson_tags,
            "knowledge_used_count": len(exp.knowledge_used) if exp.knowledge_used else 0,
            "pr_url": exp.pr_url,
            "pr_id": exp.pr_id,
            "pr_feedback_synced_at": exp.pr_feedback_synced_at,
        })
    
    return {"total": total, "runs": runs}


@router.get("/runs/{experience_id}")
async def get_run_detail(experience_id: int):
    """Get detailed information about a single run."""
    store = get_store()
    exp = store.get_by_id(experience_id)
    
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    
    return {
        "id": exp.id,
        "issue_key": exp.issue_key,
        "issue_summary": exp.issue_summary,
        "issue_description": exp.issue_description,
        "bug_type": exp.bug_type,
        
        # Analysis
        "root_cause": exp.root_cause,
        "root_cause_hypothesis": exp.root_cause_hypothesis,
        "affected_areas": exp.affected_areas,
        "suggested_approach": exp.suggested_approach,
        "confidence": exp.confidence,
        
        # Patch
        "patch_summary": exp.patch_summary,
        "files_changed": exp.files_changed,
        "patch_strategy": exp.patch_strategy,
        
        # Evolution tracking
        "difficulty_level": exp.difficulty_level,
        "first_fix_success": exp.first_fix_success,
        "iteration_count": exp.iteration_count,
        "duration_seconds": exp.duration_seconds,
        "knowledge_used": exp.knowledge_used,
        
        # Human feedback
        "human_rating": exp.human_rating,
        "human_feedback": exp.human_feedback,
        "reviewed_at": exp.reviewed_at,
        
        # Lesson
        "lesson": exp.lesson,
        "lesson_tags": exp.lesson_tags,
        "lesson_applied": exp.lesson_applied,
        
        # Metadata
        "components": exp.components,
        "labels": exp.labels,
        "run_id": exp.run_id,
        "created_at": exp.created_at,

        # PR linkage
        "pr_url": exp.pr_url,
        "pr_id": exp.pr_id,
        "pr_project": exp.pr_project,
        "pr_repo": exp.pr_repo,
        "pr_feedback_synced_at": exp.pr_feedback_synced_at,
    }


@router.post("/runs/{experience_id}/feedback")
async def submit_feedback(experience_id: int, request: FeedbackRequest):
    """Submit human feedback for a run."""
    store = get_store()
    
    # Check if experience exists
    exp = store.get_by_id(experience_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    
    success = store.submit_feedback(
        exp_id=experience_id,
        rating=request.rating,
        feedback=request.feedback,
        difficulty=request.difficulty,
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to submit feedback")
    
    return {
        "success": True,
        "experience_id": experience_id,
        "rating": request.rating,
    }


# ─── PR Feedback Sync Endpoints ────────────────────────────────────────────────

@router.post("/sync-pr-feedback/{experience_id}")
async def sync_single_pr_feedback(experience_id: int):
    """Sync feedback from a specific PR's comments to the experience."""
    from app.backend.domains.bug_fix.pr_feedback_sync import sync_pr_feedback

    store = get_store()
    exp = store.get_by_id(experience_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    if not exp.pr_project or not exp.pr_repo or not exp.pr_id:
        raise HTTPException(status_code=400, detail="Experience has no linked PR")

    result = await sync_pr_feedback(
        project=exp.pr_project,
        repo=exp.pr_repo,
        pr_id=exp.pr_id,
        experience_id=experience_id,
        store=store,
    )
    return result


@router.post("/sync-pr-feedback")
async def sync_all_pr_feedback():
    """Sync feedback from all pending PRs (experiences with PR but no rating)."""
    from app.backend.domains.bug_fix.pr_feedback_sync import sync_all_pending

    results = await sync_all_pending()
    synced = sum(1 for r in results if r.get("synced"))
    return {
        "total_checked": len(results),
        "synced": synced,
        "results": results,
    }


# ─── Experience Management Endpoints ──────────────────────────────────────────

@router.get("/experiences")
async def list_experiences(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tag: str = Query("", description="Filter by lesson tag"),
    difficulty: str = Query("", description="Filter by difficulty L1/L2/L3/L4"),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    reviewed_only: bool = Query(False),
    search: str = Query("", description="Search in issue_key/summary/lesson"),
):
    """List all experiences with filtering and pagination."""
    store = get_store()
    experiences, total = store.list_experiences(
        limit=limit,
        offset=offset,
        tag=tag,
        difficulty=difficulty,
        min_rating=min_rating,
        reviewed_only=reviewed_only,
        search=search,
    )
    
    results = []
    for exp in experiences:
        results.append({
            "id": exp.id,
            "issue_key": exp.issue_key,
            "issue_summary": exp.issue_summary,
            "bug_type": exp.bug_type,
            "difficulty_level": exp.difficulty_level,
            "lesson": exp.lesson,
            "lesson_tags": exp.lesson_tags,
            "lesson_applied": exp.lesson_applied,
            "human_rating": exp.human_rating,
            "human_feedback": exp.human_feedback,
            "reviewed_at": exp.reviewed_at,
            "created_at": exp.created_at,
        })
    
    return {"total": total, "experiences": results}


@router.get("/experiences/{experience_id}")
async def get_experience(experience_id: int):
    """Get a single experience by ID."""
    store = get_store()
    exp = store.get_by_id(experience_id)
    
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    
    return exp.to_dict()


@router.put("/experiences/{experience_id}")
async def update_experience(experience_id: int, request: ExperienceUpdateRequest):
    """Update an experience (e.g., refine lesson, adjust tags)."""
    store = get_store()
    
    # Check if experience exists
    exp = store.get_by_id(experience_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    
    # Build updates dict from non-None fields
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    success = store.update_experience(experience_id, updates)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update experience")
    
    return {"success": True, "experience_id": experience_id}


@router.delete("/experiences/{experience_id}")
async def delete_experience(experience_id: int):
    """Delete a low-quality experience."""
    store = get_store()
    
    exp = store.get_by_id(experience_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    
    success = store.delete(experience_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete experience")
    
    return {"success": True, "experience_id": experience_id}


# ─── Metrics Endpoints ────────────────────────────────────────────────────────

@router.get("/metrics")
async def get_metrics_timeline(limit: int = Query(100, ge=1, le=500)):
    """Get evolution metrics over time for charting."""
    store = get_store()
    metrics = store.get_metrics_timeline(limit=limit)
    return {"metrics": metrics}


@router.get("/metrics/summary")
async def get_metrics_summary():
    """Get aggregated metrics summary by difficulty level."""
    store = get_store()
    summary = store.get_metrics_summary()
    return summary


# ─── Health Score Endpoint ────────────────────────────────────────────────────

@router.get("/health")
async def get_health_score():
    """Get composite health score (0-100) across 4 dimensions."""
    store = get_store()
    health = store.get_health_score()
    return health
