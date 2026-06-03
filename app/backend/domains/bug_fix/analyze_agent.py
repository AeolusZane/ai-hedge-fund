"""Analyze stage — multi-phase reasoning with structured decision steps.

Phase 1: LLM classifies bug + generates search plan
Phase 2: Actual code search (grep/find) on cloned repo
Phase 3: LLM forms hypothesis from search results

Each phase emits a decision_step event via callback, building a
transparent decision tree the frontend can visualize.

Backward compatible: if no repo_path is provided, falls back to
Jira-context-only analysis (Phase 1 + Phase 3 without code search).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.llm.models import ModelProvider, get_model
from app.backend.domains.bug_fix.experience_store import ExperienceStore


# Callback types
OnToken = Callable[[str], Awaitable[None]]
OnDecisionStep = Callable[[dict[str, Any]], Awaitable[None]]


_DEFAULT_PROVIDER = os.getenv("BUG_FIX_ANALYZE_PROVIDER", "Anthropic")
_DEFAULT_MODEL = os.getenv("BUG_FIX_ANALYZE_MODEL", "claude-sonnet-4-6")
_MAX_COMMENTS = 8
_MAX_SEARCH_RESULTS = 5  # per query
_MAX_FILE_RESULTS = 10   # for file pattern search

# Skip these directories during code search
_EXCLUDE_DIRS = [
    "node_modules", ".git", "__pycache__", "dist", "build",
    ".next", "target", "vendor", ".venv", "venv",
]

# Rough token estimation: 1 token ≈ 4 chars
def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ─── Helpers ────────────────────────────────────────────────────────

def _strip_image_refs(text: str) -> str:
    """Remove Jira image attachment references from text."""
    text = re.sub(r'![^!]+\.(png|jpg|jpeg|gif|bmp|svg|webp)(\|[^!]*)?!', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[\^[^\]]+\]', '', text)
    return text.strip()


def _extract_comments(jira: dict[str, Any]) -> list[dict[str, str]]:
    """Extract comments from Jira detail (handles both raw and flattened formats)."""
    comments_raw = (
        jira.get("comment", {}).get("comments", [])
        if isinstance(jira.get("comment"), dict)
        else []
    )
    if not comments_raw and isinstance(jira.get("comments"), list):
        comments_raw = jira["comments"]

    result = []
    for c in comments_raw:
        if not isinstance(c, dict):
            continue
        author = ""
        if isinstance(c.get("author"), dict):
            author = c["author"].get("displayName", "")
        elif isinstance(c.get("author"), str):
            author = c["author"]
        body = c.get("body", "") or ""
        updated = c.get("updated", "") or c.get("created", "")
        if body.strip():
            result.append({"author": author, "body": _strip_image_refs(body.strip()), "updated": updated})
    return result


def _resolve_provider(name: str) -> ModelProvider:
    try:
        return ModelProvider(name)
    except ValueError as e:
        raise AnalyzeConfigError(f"Unknown provider {name!r}") from e


def _parse_json_response(text: str) -> dict[str, Any]:
    """Pull a JSON object out of the model's response, tolerating fences."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped
        if stripped.endswith("```"):
            stripped = stripped[: -3]
        stripped = stripped.strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].lstrip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {"raw": text.strip()}
    return parsed if isinstance(parsed, dict) else {"raw": text.strip()}


def _build_jira_context(jira: dict[str, Any]) -> str:
    """Build a text block summarizing the Jira issue for LLM consumption."""
    summary = jira.get("summary") or "(no summary)"
    description = (jira.get("description") or "(no description)")[:4000]
    comments = _extract_comments(jira)
    recent = comments[-_MAX_COMMENTS:]
    comment_block = "\n".join(
        f"- [{c.get('updated','')}] {c.get('author','?')}: {c.get('body','')[:400]}"
        for c in recent
    ) or "(no comments)"

    components = []
    for c in (jira.get("components") or []):
        if isinstance(c, dict):
            components.append(c.get("name", ""))
        elif isinstance(c, str):
            components.append(c)

    return (
        f"Summary: {summary}\n"
        f"Status: {jira.get('status','')}\n"
        f"Priority: {jira.get('priority','')}\n"
        f"Components: {', '.join(components) or '(none)'}\n"
        f"\nDescription:\n{description}\n"
        f"\nRecent comments:\n{comment_block}\n"
    )


# ─── Code Search ────────────────────────────────────────────────────

async def _grep_search(
    repo_path: Path, query: str, max_results: int = _MAX_SEARCH_RESULTS
) -> list[dict[str, Any]]:
    """Run grep on the cloned repo. Returns matches with file, line, context."""
    exclude_args = []
    for d in _EXCLUDE_DIRS:
        exclude_args.extend(["--exclude-dir", d])

    proc = await asyncio.create_subprocess_exec(
        "grep", "-rn", "-i", "--include=*.py", "--include=*.ts",
        "--include=*.tsx", "--include=*.js", "--include=*.jsx",
        "--include=*.java", "--include=*.go", "--include=*.rs",
        "--include=*.rb", "--include=*.vue", "--include=*.css",
        "--include=*.scss", "--include=*.html", "--include=*.yaml",
        "--include=*.yml", "--include=*.json", "--include=*.xml",
        *exclude_args,
        query, str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
    except asyncio.TimeoutError:
        proc.kill()
        return [{"error": f"Search timed out for '{query}'"}]

    output = stdout.decode(errors="replace").strip()
    if not output:
        return []

    results = []
    for line in output.split("\n")[:max_results]:
        parts = line.split(":", 3)
        if len(parts) < 3:
            continue
        file_path = parts[0].replace(str(repo_path) + "/", "")
        try:
            line_num = int(parts[1])
        except ValueError:
            continue
        matched_text = parts[2].strip() if len(parts) > 2 else ""

        # Read surrounding context (±2 lines)
        context_lines = []
        try:
            full_path = repo_path / file_path
            if full_path.exists() and full_path.stat().st_size < 500_000:
                all_lines = full_path.read_text(errors="replace").split("\n")
                start = max(0, line_num - 3)
                end = min(len(all_lines), line_num + 2)
                context_lines = [
                    {"line": i + 1, "text": all_lines[i]}
                    for i in range(start, end)
                ]
        except Exception:
            pass

        results.append({
            "file": file_path,
            "line": line_num,
            "match": matched_text[:200],
            "context": context_lines,
        })
    return results


async def _find_files(
    repo_path: Path, pattern: str, max_results: int = _MAX_FILE_RESULTS
) -> list[dict[str, Any]]:
    """Find files matching a name pattern in the repo."""
    proc = await asyncio.create_subprocess_exec(
        "find", str(repo_path),
        "-name", ".git", "-prune", "-o",
        "-name", "node_modules", "-prune", "-o",
        "-name", "__pycache__", "-prune", "-o",
        "-name", pattern, "-print",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except asyncio.TimeoutError:
        proc.kill()
        return []

    output = stdout.decode(errors="replace").strip()
    if not output:
        return []

    results = []
    for line in output.split("\n")[:max_results]:
        file_path = line.replace(str(repo_path) + "/", "")
        results.append({"file": file_path})
    return results


async def _run_code_search(
    repo_path: Path, queries: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Execute all search queries against the repo. Returns aggregated results."""
    all_results = []

    for q in queries[:5]:  # max 5 queries
        q_type = q.get("type", "grep")
        q_query = q.get("query", "")
        q_reason = q.get("reason", "")

        if not q_query:
            continue

        if q_type == "file":
            files = await _find_files(repo_path, q_query)
            all_results.append({
                "query": q_query,
                "type": "file_search",
                "reason": q_reason,
                "results": files,
                "match_count": len(files),
            })
        else:
            matches = await _grep_search(repo_path, q_query)
            all_results.append({
                "query": q_query,
                "type": "code_search",
                "reason": q_reason,
                "results": matches,
                "match_count": len(matches),
            })

    return all_results


# ─── LLM Phases ─────────────────────────────────────────────────────

_PHASE1_PROMPT = """\
You are a senior engineer investigating a bug. Based on the Jira issue below, \
create a search plan to investigate the root cause in the codebase.

{experience_context}

{jira_context}

Return ONLY a JSON object (no prose, no markdown fences):
{{
  "bug_type": "one of: null_pointer, logic_error, race_condition, config_issue, api_contract, data_flow, ui_bug, performance, security, other",
  "bug_type_reasoning": "1-2 sentences on why you classified it this way",
  "search_queries": [
    {{
      "query": "exact search term for grep (short, precise)",
      "type": "grep or file",
      "reason": "why this search will help narrow down the root cause"
    }}
  ],
  "likely_areas": ["specific files, modules, or components to investigate"],
  "initial_hypothesis": "your best guess at the root cause based on the bug description alone"
}}

Rules:
- Generate 2-4 search queries that are specific enough to find relevant code
- Use "grep" type for searching code content (error messages, function names, class names, variable names)
- Use "file" type for finding files by name pattern (e.g., "*.Service.java", "useAuth*")
- Keep grep queries short (1-3 words) for better match rates
"""


_PHASE3_PROMPT = """\
You are a senior engineer who has investigated a bug. You started with a Jira \
issue and searched the codebase. Now form your root cause hypothesis.

{experience_context}

## Jira Issue
{jira_context}

## Code Search Results
{search_results_text}

Return ONLY a JSON object (no prose, no markdown fences):
{{
  "decision_steps": [
    {{
      "step": "classify_bug",
      "description": "Classified bug type and reasoning",
      "details": {{
        "bug_type": "the type",
        "reasoning": "why this classification"
      }},
      "confidence": 0.0
    }},
    {{
      "step": "search_codebase",
      "description": "What was searched and what was found",
      "details": {{
        "queries_executed": 0,
        "total_matches": 0,
        "key_findings": ["most relevant findings from code search"]
      }},
      "confidence": 0.0
    }},
    {{
      "step": "form_hypothesis",
      "description": "Root cause hypothesis based on all evidence",
      "details": {{
        "hypothesis": "the root cause hypothesis",
        "evidence_chain": ["evidence 1", "evidence 2"],
        "alternatives": [
          {{"hypothesis": "alternative explanation", "confidence": 0.0}}
        ]
      }},
      "confidence": 0.0
    }}
  ],
  "root_cause_hypothesis": "concise root cause (1-2 sentences)",
  "affected_areas": ["files/modules to fix"],
  "suggested_approach": ["step 1", "step 2", "step 3"],
  "open_questions": ["things still unclear"]
}}

Rules:
- confidence is 0.0-1.0 (how sure you are about this step's conclusion)
- decision_steps must have exactly 3 steps: classify_bug, search_codebase, form_hypothesis
- key_findings should be the 3-5 most relevant code search results
- alternatives should list 1-3 other possible explanations with lower confidence
- evidence_chain links the Jira symptoms to the code findings to the hypothesis
"""


async def _llm_invoke(
    llm, prompt: str, on_token: Optional[OnToken] = None
) -> tuple[str, dict[str, int]]:
    """Invoke LLM with optional streaming. Returns (text, usage_info)."""
    usage = {"input_tokens": 0, "output_tokens": 0}

    if on_token is None:
        response = await llm.ainvoke(prompt)
        content = getattr(response, "content", response)
        text = content if isinstance(content, str) else str(content)
        # Try to extract usage from response
        um = getattr(response, "usage_metadata", None) or getattr(response, "token_usage", None)
        if isinstance(um, dict):
            usage["input_tokens"] = um.get("input_tokens", 0) or um.get("prompt_tokens", 0)
            usage["output_tokens"] = um.get("output_tokens", 0) or um.get("completion_tokens", 0)
        else:
            usage["input_tokens"] = _estimate_tokens(prompt)
            usage["output_tokens"] = _estimate_tokens(text)
        return text, usage

    # Streaming path
    parts: list[str] = []
    async for chunk in llm.astream(prompt):
        piece = getattr(chunk, "content", chunk)
        if isinstance(piece, str):
            token = piece
        elif isinstance(piece, list):
            token_parts = []
            for block in piece:
                if isinstance(block, dict) and block.get("type") == "text":
                    token_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    token_parts.append(block)
            token = "".join(token_parts)
        else:
            token = str(piece)
        if not token:
            continue
        parts.append(token)
        try:
            await on_token(token)
        except Exception:
            pass

    text = "".join(parts)
    usage["input_tokens"] = _estimate_tokens(prompt)
    usage["output_tokens"] = _estimate_tokens(text)
    return text, usage


# ─── Main Entry Point ───────────────────────────────────────────────

class AnalyzeConfigError(RuntimeError):
    """Raised when the chosen provider's credentials are missing."""


async def analyze_jira_issue(
    jira_detail: dict[str, Any],
    *,
    model_name: Optional[str] = None,
    model_provider: Optional[str] = None,
    api_keys: Optional[dict[str, str]] = None,
    on_token: Optional[OnToken] = None,
    on_decision_step: Optional[OnDecisionStep] = None,
    repo_path: Optional[str] = None,
) -> dict[str, Any]:
    """Multi-phase bug analysis with structured decision steps.

    Phase 1: LLM classifies bug + generates search plan
    Phase 2: Actual code search on cloned repo (if repo_path provided)
    Phase 3: LLM forms hypothesis from search results

    Each phase emits a decision_step via on_decision_step callback.
    The final return value includes the full decision tree + analysis result.
    """
    chosen_model = model_name or _DEFAULT_MODEL
    chosen_provider = _resolve_provider(model_provider or _DEFAULT_PROVIDER)

    try:
        llm = get_model(chosen_model, chosen_provider, api_keys=api_keys or {})
    except Exception as e:
        raise AnalyzeConfigError(str(e)) from e
    if llm is None:
        raise AnalyzeConfigError(
            f"get_model returned None for {chosen_provider.value}/{chosen_model}"
        )

    jira_context = _build_jira_context(jira_detail)
    total_usage = {"input_tokens": 0, "output_tokens": 0}

    # ── Phase 0: Knowledge Recall ───────────────────────────────────
    # Query two knowledge sources in parallel:
    #   1. experience_store — team's own bug fix history (FTS5)
    #   2. pr_embedding — historical PR review records (TF-IDF semantic)
    experience_context = ""
    similar_cases: list[dict[str, Any]] = []
    pr_references: list[dict[str, Any]] = []
    query_text = f"{jira_detail.get('summary', '')} {jira_detail.get('description', '')[:300]}"

    # Source 1: Experience Store (local SQLite + FTS5)
    try:
        store = ExperienceStore()
        experiences = store.search_similar(query_text, limit=3, min_confidence=0.3)
        if experiences:
            case_texts = []
            for i, exp in enumerate(experiences, 1):
                case_texts.append(
                    f"### Historical Case #{i}: {exp.issue_key}\n"
                    f"- Bug type: {exp.bug_type}\n"
                    f"- Root cause: {exp.root_cause}\n"
                    f"- Fix strategy: {exp.patch_strategy or '(not recorded)'}\n"
                    f"- Files changed: {', '.join(exp.files_changed) or '(not recorded)'}\n"
                    f"- Confidence: {exp.confidence:.0%}\n"
                )
                similar_cases.append({
                    "id": exp.id,
                    "issue_key": exp.issue_key,
                    "bug_type": exp.bug_type,
                    "root_cause": exp.root_cause,
                    "confidence": exp.confidence,
                    "files_changed": exp.files_changed,
                })
            experience_context += (
                "## Historical Similar Cases (from team knowledge base)\n"
                "The following cases were previously solved by the team. "
                "Use them as reference — the current bug may share the same root cause.\n\n"
                + "\n".join(case_texts) + "\n"
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Experience recall failed: {e}")

    # Source 2: PR Embedding Service (semantic search over PR reviews)
    try:
        from app.backend.domains.bug_fix.pr_embedding_client import search_similar_prs
        pr_results = await search_similar_prs(query_text, n=5)
        if pr_results:
            pr_texts = []
            for i, ref in enumerate(pr_results, 1):
                pr_texts.append(
                    f"### PR Review #{i}: PR #{ref['pr_id']} — {ref.get('issue_type', 'unknown')}\n"
                    f"- PR title: {ref.get('pr_title', '')}\n"
                    f"- Module: {ref.get('module', 'unknown')}\n"
                    f"- File: {ref.get('file_path', 'unknown')}\n"
                    f"- Reviewer: {ref.get('reviewer', 'unknown')}\n"
                    f"- Comment: {ref['comment']}\n"
                )
                pr_references.append(ref)
            experience_context += (
                "\n## Historical PR Review Context\n"
                "The following similar issues were flagged in past PR reviews. "
                "Use them as reference patterns but do not copy verbatim.\n\n"
                + "\n".join(pr_texts)
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"PR embedding search failed: {e}")

    # Emit knowledge recall decision step
    total_knowledge = len(similar_cases) + len(pr_references)
    recall_step = {
        "step": "knowledge_recall",
        "description": f"Found {len(similar_cases)} cases + {len(pr_references)} PR reviews" if total_knowledge else "No historical knowledge found",
        "details": {
            "experience_cases": len(similar_cases),
            "pr_references": len(pr_references),
            "cases": similar_cases,
            "pr_refs": [{"pr_id": r["pr_id"], "issue_type": r.get("issue_type", "")} for r in pr_references],
            "mode": "reuse" if total_knowledge else "generate",
        },
        "confidence": 0.85 if total_knowledge else 0.0,
    }
    if on_decision_step:
        await on_decision_step(recall_step)

    # ── Phase 1: Search Plan ────────────────────────────────────────
    phase1_prompt = _PHASE1_PROMPT.format(
        jira_context=jira_context,
        experience_context=experience_context,
    )
    phase1_text, phase1_usage = await _llm_invoke(llm, phase1_prompt, on_token)
    total_usage["input_tokens"] += phase1_usage["input_tokens"]
    total_usage["output_tokens"] += phase1_usage["output_tokens"]

    search_plan = _parse_json_response(phase1_text)
    search_queries = search_plan.get("search_queries", [])

    step1 = {
        "step": "classify_bug",
        "description": f"Classified as {search_plan.get('bug_type', 'unknown')}",
        "details": {
            "bug_type": search_plan.get("bug_type", "unknown"),
            "reasoning": search_plan.get("bug_type_reasoning", ""),
            "initial_hypothesis": search_plan.get("initial_hypothesis", ""),
            "likely_areas": search_plan.get("likely_areas", []),
        },
        "confidence": 0.5,
    }
    if on_decision_step:
        await on_decision_step(step1)

    # ── Phase 2: Code Search ────────────────────────────────────────
    search_results: list[dict[str, Any]] = []
    if repo_path and search_queries:
        rp = Path(repo_path)
        if rp.exists() and (rp / ".git").exists():
            search_results = await _run_code_search(rp, search_queries)

    total_matches = sum(r.get("match_count", 0) for r in search_results)
    key_findings = []
    for r in search_results:
        for m in (r.get("results") or [])[:2]:
            if isinstance(m, dict) and "match" in m:
                key_findings.append(f"{m['file']}:{m.get('line', '?')} — {m['match'][:100]}")
            elif isinstance(m, dict) and "file" in m:
                key_findings.append(f"Found file: {m['file']}")

    step2 = {
        "step": "search_codebase",
        "description": f"Searched {len(search_queries)} queries, {total_matches} matches",
        "details": {
            "queries": [
                {"query": r["query"], "type": r["type"], "matches": r["match_count"]}
                for r in search_results
            ],
            "total_matches": total_matches,
            "key_findings": key_findings[:8],
        },
        "confidence": min(0.8, 0.3 + total_matches * 0.05),
    }
    if on_decision_step:
        await on_decision_step(step2)

    # ── Phase 3: Hypothesis ─────────────────────────────────────────
    search_results_text = json.dumps(search_results, indent=2, ensure_ascii=False)[:3000]
    if not search_results:
        search_results_text = "(No code search performed — repo not available)"

    phase3_prompt = _PHASE3_PROMPT.format(
        jira_context=jira_context,
        search_results_text=search_results_text,
        experience_context=experience_context,
    )
    phase3_text, phase3_usage = await _llm_invoke(llm, phase3_prompt, on_token)
    total_usage["input_tokens"] += phase3_usage["input_tokens"]
    total_usage["output_tokens"] += phase3_usage["output_tokens"]

    analysis = _parse_json_response(phase3_text)

    # Ensure decision_steps exist (LLM might not follow the schema perfectly)
    if "decision_steps" not in analysis or not isinstance(analysis["decision_steps"], list):
        analysis["decision_steps"] = [step1, step2, {
            "step": "form_hypothesis",
            "description": analysis.get("root_cause_hypothesis", "Hypothesis formed"),
            "details": {
                "hypothesis": analysis.get("root_cause_hypothesis", ""),
                "evidence_chain": [],
                "alternatives": [],
            },
            "confidence": 0.6,
        }]

    # Emit final step
    step3_data = analysis["decision_steps"][-1] if len(analysis["decision_steps"]) >= 3 else {
        "step": "form_hypothesis",
        "description": analysis.get("root_cause_hypothesis", ""),
        "details": analysis,
        "confidence": 0.6,
    }
    if on_decision_step:
        await on_decision_step(step3_data)

    # ── Token tracking ──────────────────────────────────────────────
    analysis["_token_usage"] = {
        "input_tokens": total_usage["input_tokens"],
        "output_tokens": total_usage["output_tokens"],
        "total_tokens": total_usage["input_tokens"] + total_usage["output_tokens"],
        "model": chosen_model,
        "provider": chosen_provider.value,
    }

    return analysis
