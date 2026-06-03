"""Experience API routes — search, list, stats, seed."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Any, Optional

from app.backend.domains.bug_fix.experience_store import ExperienceStore

router = APIRouter(prefix="/api/v1/experiences", tags=["experiences"])


class SearchRequest(BaseModel):
    query: str
    bug_type: str = ""
    limit: int = 5
    min_confidence: float = 0.0


class ExperienceResponse(BaseModel):
    id: int
    created_at: str
    issue_key: str
    issue_summary: str
    bug_type: str
    root_cause: str
    root_cause_hypothesis: str
    affected_areas: list[str]
    suggested_approach: list[str]
    confidence: float
    patch_summary: str
    files_changed: list[str]
    patch_strategy: str
    gate_action: str
    human_context: str
    components: list[str]
    labels: list[str]
    run_id: str
    token_usage: dict[str, Any]


class StatsResponse(BaseModel):
    total: int
    approved: int
    avg_confidence: float
    bug_types: dict[str, int]


class SeedRequest(BaseModel):
    """Request body for seeding example experiences."""
    pass  # No params needed — seeds are built-in


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get aggregate stats about stored experiences."""
    store = ExperienceStore()
    return store.get_stats()


@router.post("/search", response_model=list[ExperienceResponse])
async def search_experiences(req: SearchRequest):
    """Search for similar experiences using full-text search."""
    store = ExperienceStore()
    results = store.search_similar(
        req.query,
        bug_type=req.bug_type,
        limit=req.limit,
        min_confidence=req.min_confidence,
    )
    return [
        ExperienceResponse(
            id=exp.id or 0,
            created_at=exp.created_at or "",
            issue_key=exp.issue_key,
            issue_summary=exp.issue_summary,
            bug_type=exp.bug_type,
            root_cause=exp.root_cause,
            root_cause_hypothesis=exp.root_cause_hypothesis,
            affected_areas=exp.affected_areas,
            suggested_approach=exp.suggested_approach,
            confidence=exp.confidence,
            patch_summary=exp.patch_summary,
            files_changed=exp.files_changed,
            patch_strategy=exp.patch_strategy,
            gate_action=exp.gate_action,
            human_context=exp.human_context,
            components=exp.components,
            labels=exp.labels,
            run_id=exp.run_id,
            token_usage=exp.token_usage,
        )
        for exp in results
    ]


@router.get("/recent", response_model=list[ExperienceResponse])
async def list_recent(
    limit: int = Query(20, ge=1, le=100),
):
    """List most recent experiences."""
    store = ExperienceStore()
    results = store.list_recent(limit=limit)
    return [
        ExperienceResponse(
            id=exp.id or 0,
            created_at=exp.created_at or "",
            issue_key=exp.issue_key,
            issue_summary=exp.issue_summary,
            bug_type=exp.bug_type,
            root_cause=exp.root_cause,
            root_cause_hypothesis=exp.root_cause_hypothesis,
            affected_areas=exp.affected_areas,
            suggested_approach=exp.suggested_approach,
            confidence=exp.confidence,
            patch_summary=exp.patch_summary,
            files_changed=exp.files_changed,
            patch_strategy=exp.patch_strategy,
            gate_action=exp.gate_action,
            human_context=exp.human_context,
            components=exp.components,
            labels=exp.labels,
            run_id=exp.run_id,
            token_usage=exp.token_usage,
        )
        for exp in results
    ]


@router.get("/{exp_id}", response_model=ExperienceResponse)
async def get_experience(exp_id: int):
    """Get a single experience by ID."""
    store = ExperienceStore()
    exp = store.get_by_id(exp_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    return ExperienceResponse(
        id=exp.id or 0,
        created_at=exp.created_at or "",
        issue_key=exp.issue_key,
        issue_summary=exp.issue_summary,
        bug_type=exp.bug_type,
        root_cause=exp.root_cause,
        root_cause_hypothesis=exp.root_cause_hypothesis,
        affected_areas=exp.affected_areas,
        suggested_approach=exp.suggested_approach,
        confidence=exp.confidence,
        patch_summary=exp.patch_summary,
        files_changed=exp.files_changed,
        patch_strategy=exp.patch_strategy,
        gate_action=exp.gate_action,
        human_context=exp.human_context,
        components=exp.components,
        labels=exp.labels,
        run_id=exp.run_id,
        token_usage=exp.token_usage,
    )


@router.delete("/{exp_id}")
async def delete_experience(exp_id: int):
    """Delete an experience."""
    store = ExperienceStore()
    deleted = store.delete(exp_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Experience not found")
    return {"deleted": True, "id": exp_id}


@router.post("/seed")
async def seed_experiences():
    """Seed the experience store with example cases for demo purposes.

    Creates 5 realistic bug fix experiences that represent common
    patterns a team would accumulate over time.
    """
    from app.backend.domains.bug_fix.experience_store import Experience

    store = ExperienceStore()

    seeds = [
        Experience(
            issue_key="PROJ-101",
            issue_summary="Login page CSS misalignment on mobile devices",
            issue_description="The login form container overflows on screens smaller than 375px. "
                "The flex container doesn't wrap properly, causing the submit button to be cut off.",
            bug_type="ui_bug",
            root_cause="Flex container missing flex-wrap: wrap property, causing child elements "
                "to overflow instead of wrapping on small screens.",
            root_cause_hypothesis="The .login-form-container uses display: flex but lacks "
                "flex-wrap: wrap, so on narrow viewports the children overflow the container.",
            affected_areas=["src/components/LoginForm.tsx", "src/styles/login.css"],
            suggested_approach=[
                "Add flex-wrap: wrap to .login-form-container",
                "Add max-width: 100% to child elements",
                "Test on 320px, 375px, and 414px viewports"
            ],
            confidence=0.92,
            patch_summary="Added flex-wrap and responsive max-width constraints",
            files_changed=["src/components/LoginForm.tsx", "src/styles/login.css"],
            patch_strategy="Add flex-wrap: wrap → Add max-width: 100% → Test responsive breakpoints",
            gate_action="approve",
            components=["Frontend", "UI"],
            labels=["css", "responsive", "mobile"],
            run_id="seed-001",
        ),
        Experience(
            issue_key="PROJ-205",
            issue_summary="NullPointerException in UserService.getProfile after OAuth callback",
            issue_description="After a user logs in via Google OAuth, the getProfile endpoint "
                "throws NPE. The user record exists in DB but the profile field is null.",
            bug_type="null_pointer",
            root_cause="OAuth callback creates the user record but doesn't initialize the "
                "profile sub-document. getProfile() accesses user.profile.name without null check.",
            root_cause_hypothesis="The OAuth flow creates users with a null profile field. "
                "The getProfile endpoint assumes profile is always populated.",
            affected_areas=["src/services/UserService.java", "src/auth/OAuthCallback.java"],
            suggested_approach=[
                "Initialize empty profile object in OAuthCallback.createUser()",
                "Add null check in UserService.getProfile()",
                "Add integration test for OAuth → getProfile flow"
            ],
            confidence=0.88,
            patch_summary="Initialize profile in OAuth flow + add defensive null check",
            files_changed=["src/auth/OAuthCallback.java", "src/services/UserService.java"],
            patch_strategy="Initialize profile object → Add null guard → Add integration test",
            gate_action="approve",
            components=["Backend", "Auth"],
            labels=["npe", "oauth", "user-profile"],
            run_id="seed-002",
        ),
        Experience(
            issue_key="PROJ-312",
            issue_summary="Dashboard API response time degrades to 8+ seconds under load",
            issue_description="The /api/dashboard endpoint takes 8+ seconds when there are "
                "more than 100 active users. The endpoint makes N+1 queries to fetch user stats.",
            bug_type="performance",
            root_cause="N+1 query pattern: the dashboard endpoint fetches the user list, then "
                "makes a separate DB query for each user's stats. With 100+ users this becomes "
                "100+ sequential queries.",
            root_cause_hypothesis="N+1 query in DashboardController.getStats() — iterates users "
                "and calls statsRepository.findByUserId() for each one.",
            affected_areas=["src/controllers/DashboardController.java", "src/repositories/StatsRepository.java"],
            suggested_approach=[
                "Replace N+1 with a single batch query using IN clause",
                "Add database index on stats.user_id",
                "Add response time assertion in integration test (< 2s)"
            ],
            confidence=0.95,
            patch_summary="Replaced N+1 queries with batch IN clause + added DB index",
            files_changed=["src/controllers/DashboardController.java", "src/repositories/StatsRepository.java", "db/migrations/004_add_stats_index.sql"],
            patch_strategy="Batch query with IN → Add DB index → Add perf assertion",
            gate_action="approve",
            components=["Backend", "Performance"],
            labels=["n-plus-1", "performance", "database"],
            run_id="seed-003",
        ),
        Experience(
            issue_key="PROJ-418",
            issue_summary="Race condition in inventory deduction during concurrent checkout",
            issue_description="When two users checkout the same item simultaneously, inventory "
                "can go negative. The read-then-write pattern is not atomic.",
            bug_type="race_condition",
            root_cause="InventoryService.deductStock() reads current stock, checks if sufficient, "
                "then writes the new value. Two concurrent requests can both read the same stock "
                "value before either writes, leading to double deduction.",
            root_cause_hypothesis="Non-atomic read-then-write in deductStock(). No database "
                "locking or optimistic concurrency control.",
            affected_areas=["src/services/InventoryService.java", "src/models/Inventory.java"],
            suggested_approach=[
                "Use SELECT ... FOR UPDATE to lock the row during deduction",
                "Add optimistic locking with version column as fallback",
                "Add concurrent checkout integration test"
            ],
            confidence=0.85,
            patch_summary="Added SELECT FOR UPDATE lock + optimistic version column",
            files_changed=["src/services/InventoryService.java", "src/models/Inventory.java", "db/migrations/005_add_inventory_version.sql"],
            patch_strategy="Row-level lock with FOR UPDATE → Add version column → Concurrent test",
            gate_action="approve",
            components=["Backend", "Data"],
            labels=["race-condition", "concurrency", "inventory"],
            run_id="seed-004",
        ),
        Experience(
            issue_key="PROJ-527",
            issue_summary="API returns 500 when request body contains emoji characters",
            issue_description="POST /api/comments returns 500 Internal Server Error when the "
                "comment body contains emoji like 🎉 or 👍. The database column uses utf8 charset "
                "which doesn't support 4-byte UTF-8 characters.",
            bug_type="config_issue",
            root_cause="MySQL table uses utf8 charset (3-byte max) instead of utf8mb4 (4-byte). "
                "Emoji characters require 4 bytes, causing an insertion error that's not caught.",
            root_cause_hypothesis="Database charset mismatch: utf8 vs utf8mb4. The error is "
                "thrown as an unhandled exception instead of a validation error.",
            affected_areas=["db/schema.sql", "src/controllers/CommentController.java"],
            suggested_approach=[
                "ALTER TABLE to use utf8mb4 charset",
                "Add input validation for character encoding",
                "Add error handling for charset-related DB errors"
            ],
            confidence=0.90,
            patch_summary="Migrated charset to utf8mb4 + added input validation",
            files_changed=["db/migrations/006_utf8mb4.sql", "src/controllers/CommentController.java"],
            patch_strategy="ALTER TABLE charset → Add input validation → Add error handler",
            gate_action="approve",
            components=["Backend", "Database"],
            labels=["charset", "utf8mb4", "emoji", "mysql"],
            run_id="seed-005",
        ),
    ]

    stored_ids = []
    for seed in seeds:
        exp_id = store.store(seed)
        stored_ids.append(exp_id)

    return {
        "seeded": len(stored_ids),
        "ids": stored_ids,
        "total": store.count(),
    }
