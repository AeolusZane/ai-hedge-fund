# Bug Fix Domain — Roadmap

Status as of this commit: F3a (Analyze), F3b (Patch), and F3d (Open PR)
are landed end-to-end. F3c (Test) deliberately stays stubbed because
the user opted to defer it.

## Where each stage stands

| Stage              | Real / stub | Notes |
| ------------------ | ----------- | ----- |
| Jira Issue Input   | real        | merged with Fetch Jira; performs MCP fetch as the first runnable node; fail-fast |
| Repo Path Input    | real        | runnable input node; writes `state["repo_path"]` for Patch / Open PR |
| PR Config          | real        | runnable input node; writes `state["pr_project"]`, `state["pr_repo"]`, `state["pr_target_branch"]` |
| Analyze            | real        | LLM call via `get_model(model_name, model_provider, api_keys)`; per-node selector |
| Patch              | real        | spawns the `claude` CLI in `state["repo_path"]`, captures `git diff` + touched files |
| Test               | stub        | F3c — deferred at user's request |
| Open PR            | real        | `git checkout -B fix/<key>` → commit → push → Bitbucket MCP `bitbucket_create_pr` |

## Architecture invariants already established

- One backend executor per domain registered through
  `executor_registry.register(...)` at `app.backend.domains.<id>.pack` import time.
- `BugFixExecutor.run()` walks the React Flow graph in topological order
  (`_topological_order`, Kahn's algorithm). Each runnable node is one
  stage; node ids on the canvas match progress-event ids.
- Per-node config (e.g. model selection on Analyze) is folded into
  `node.data` at submit time by the frontend (`run-dialog.tsx`) and
  read back in `_run_node` via `node_data`.
- A failed Jira fetch raises `JiraFetchError`; the route wraps it as
  `RuntimeError` so the SSE consumer surfaces the error and stops.

These should NOT be undone by F3 work.

## F3b — Patch (real)

### Goal

Edit code in a target repo so the bug is fixed, leaving a clean diff
ready for review. No autonomous merging.

### Open design questions

1. **Edit mechanism** — three plausible paths:
   - `claude` CLI as a subprocess (Claude Code). Pros: best code agent
     available; supports tools natively. Cons: extra binary dep; harder
     to programmatically observe progress.
   - LangChain agent calling explicit file-edit tools we expose. Pros:
     fully in-process, observable. Cons: we have to build/host the
     tools; quality lower than Claude Code.
   - LLM produces a unified diff that we apply with `patch`/`git apply`.
     Pros: small, debuggable. Cons: brittle when context drifts; LLM
     often hallucinates line numbers.
   - **Lean recommendation**: start with Claude Code subprocess. It's
     the only option that produces real edits with reasonable quality
     today.
2. **Target repo location** — needs a canvas node ("Repo Path Input")
   or a config carried on the Patch node. Don't hard-code.
3. **Branch policy** — auto-create `fix/<issue-key>` off `main` (or a
   user-configurable base). Branch name is already in `result.branch`
   but we don't create it today.
4. **Working tree contamination** — must NOT touch uncommitted state in
   the user's actual working tree. Use a git worktree under
   `/tmp/bug-fix/<run-id>/` or similar.
5. **Status / progress** — Patch is long-running (minutes). Need
   intermediate progress events (file-by-file). Map them onto the
   canvas tile so the user sees something.

### Available infrastructure

- `git-mcp` MCP server in
  `/Users/zhangjingzheng/Desktop/ai/Test/Aeolus/mcp/git-mcp` —
  inspect for branch/clone/diff tools.
- Possibly Claude Code CLI on the user's machine. Check `which claude`.

### Scope cut for first pass

Don't try to autonomously fix complex bugs. Limit to:

- Single-repo, single-file edits.
- Skip if Analyze's `affected_areas` is empty.
- Emit a single `Patch` progress event per file edited.
- Result includes a list of `files_changed` plus the raw diff.

## F3c — Test (real)

### Goal

Verify the patch by running the project's tests; fail the run if they
don't pass.

### Open design questions

1. **Which command?** Per-repo. Options:
   - Canvas node "Test Config" carrying the command string.
   - Convention: `<repo>/.bugfix/test.sh` if present.
   - Recommendation: Test Config node, persist via `useNodeState`.
2. **Subprocess vs container** — direct subprocess is simplest but
   trusts the command. Containers (Docker) are safer but heavyweight.
   For first pass: direct subprocess.
3. **What counts as failure?** Exit code != 0 → fail. Surface stdout
   tail (last ~50 lines) in the Done payload.
4. **Timeout** — needs one. Default 5 minutes, configurable on the node.

### Scope cut for first pass

- Subprocess `bash -c <cmd>` from the repo path used by Patch.
- Timeout: 300s default, override via node config.
- Emit `Test` progress with "Running tests / Done / Failed".
- Result: `tests_passed: bool`, `tests_output_tail: str`.

## F3d — Open PR (real)

### Goal

Push the fix branch and open a PR on Bitbucket pointing at the Jira
issue. No auto-merge.

### Open design questions

1. **Bitbucket MCP** — user has
   `/Users/zhangjingzheng/Desktop/ai/Test/Aeolus/mcp/bitbucket`. Inspect
   for available tools (`pullrequest_create`?, `git_push`?, etc.).
2. **Git push** — branch needs to exist remotely. The MCP may handle
   this; otherwise call `git push --set-upstream` from a subprocess.
3. **PR body** — auto-fill with:
   - Title: `<issue-key>: <jira summary>`
   - Body: link back to Jira + Analyze hypothesis + Patch summary.
4. **Reviewer policy** — probably leave reviewers empty for v1.

### Scope cut for first pass

- Reuse Bitbucket MCP tool to create PR.
- Source: branch made in Patch. Target: configurable, default `main`.
- Result: `pr_url`, `pr_id`.

## Anthropic-compatible providers

Both the Patch stage (`claude` CLI subprocess) and the Analyze stage
(when an `Anthropic` model is selected) honour `ANTHROPIC_BASE_URL`.
Setting it to e.g. `https://api.deepseek.com/anthropic` routes every
Anthropic-shaped call through that provider; the `ANTHROPIC_API_KEY`
should then hold the provider's key. No code changes are needed — the
override works because:

- `patch_agent._run(...)` calls `asyncio.create_subprocess_exec` without
  an `env=` override, so `claude` inherits the parent's env (which has
  the .env values via `load_dotenv()` in `app/backend/main.py`).
- `src/llm/models.py::get_model` constructs `ChatAnthropic` without an
  explicit `base_url` / `anthropic_api_url`, so the underlying
  `anthropic.Anthropic` client reads `ANTHROPIC_BASE_URL` from env.

When routing through such a proxy the `claude` CLI also needs the
family-alias → real-model mapping:

```
ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro
ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro
ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-pro
```

Without these the CLI hands the proxy ids like `claude-sonnet-4-6`
that the upstream provider won't recognise. The Analyze stage isn't
affected — it picks the model id explicitly on each node.

If we ever decide to support per-stage base URLs, the place to plumb
them in is `node_data` (consumed by `_do_patch` / `_do_analyze`), not
a global flag.

## Cross-cutting concerns

- **Cancellation** — `context.is_cancelled()` is checked before each
  stage. Long stages (Patch / Test) should poll it during work too.
- **Per-node model selection** — already supported via
  `STAGES_THAT_USE_AN_LLM`. When Patch lands, add it to that set so the
  selector renders on Patch nodes.
- **Per-node config persistence** — `useNodeState(id, 'key', default)`.
  Snapshot lifted into `node.data` by `run-dialog.tsx`. Mirror this for
  Repo Path, Test Config, PR Config when needed.
- **Result payload growth** — be careful: `FlowRun.results` is a JSON
  blob stored in SQLite. Patch diffs can be large; cap at e.g. 100 KB
  and put the rest behind a separate fetch if necessary.

## Suggested execution order

1. **F3b/Patch first** with the smallest possible scope (Claude Code
   single-file edit, in a temp worktree). Gives the most leverage.
2. **F3d/Open PR** next; it's relatively self-contained once a branch
   with the diff exists.
3. **F3c/Test** last; it's the cheapest to bolt on between Patch and
   Open PR, and the easiest to make optional.

## Non-goals (deliberately out of scope)

- Multi-repo or monorepo workspaces.
- Auto-merging PRs.
- Spawning sub-agents inside Patch (just call Claude Code, don't
  re-implement an agent).
- Replacing the Jira MCP with a direct REST client.
