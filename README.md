# AI Agent Platform

A self-evolving AI agent platform that learns from experience. The platform provides infrastructure for building, running, and monitoring autonomous agents that improve over time.

## Current Domain: Bug Fix Agent

An autonomous agent that fetches bugs from Jira, analyzes code, generates patches, runs tests, and submits PRs. The key innovation: **it accumulates project knowledge over time and gets better at fixing bugs.**

### Self-Evolution Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Bug Fix Pipeline                       │
│                                                          │
│  Jira Bug → Analyze → Patch → Test → PR → Post-fix      │
│               ↑                              │           │
│               │         Knowledge Loop        │           │
│               └──────────────────────────────┘           │
│                                                          │
│  Three Knowledge Layers:                                 │
│  ├── ExperienceStore     — bug patterns & lessons        │
│  ├── CodeUnderstanding   — file-level code summaries     │
│  └── PR Embedding        — historical PR review comments │
└─────────────────────────────────────────────────────────┘
```

### How it Learns

| Phase | What happens | Knowledge gained |
|-------|-------------|-----------------|
| Analyze (Phase 1) | Search experiences + PR reviews | Knowledge Recall |
| Analyze (Phase 2) | Read code, trace call chains | — |
| Analyze (Phase 2.5) | Check code understanding cache | Cache hit / verify stale |
| Patch (Phase 3) | Generate fix with historical context | — |
| Test (Phase 4) | Run tests, iterate if failed | — |
| Post-fix (Phase 5) | Extract lessons from the fix | New experience stored |

**The flywheel:**

```
Fix bug → Store experience → Next bug search hits it → Better hypothesis → Faster fix
```

### Key Features

- **6-phase pipeline:** Fetch → Analyze → Patch → Test → PR → Post-fix
- **Knowledge accumulation:** Three-layer memory (experiences, code understanding, PR reviews)
- **Stale detection:** Code understanding cache verifies freshness via git hash + LLM validation
- **PR Review sync:** Nightly sync of Bitbucket PR review comments into searchable vector store
- **Web dashboard:** Real-time pipeline visualization at `/bug-fix`
- **Automated scheduling:** Cron-based daily bug fetching + PR sync

## Project Structure

```
ai-hedge-fund/
├── app/
│   ├── backend/                  # FastAPI backend
│   │   ├── domains/
│   │   │   └── bug_fix/          # Self-evolving bug fix agent
│   │   │       ├── analyze_agent.py
│   │   │       ├── patch_agent.py
│   │   │       ├── test_agent.py
│   │   │       ├── pr_agent.py
│   │   │       ├── post_fix_agent.py
│   │   │       ├── experience_store.py
│   │   │       ├── code_understanding_store.py
│   │   │       ├── pr_embedding/
│   │   │       └── pr_sync.py
│   │   ├── routes/               # API routes
│   │   ├── database/             # SQLite + models
│   │   ├── repositories/         # Data access layer
│   │   └── main.py
│   └── frontend/                 # React + Vite frontend
│       └── src/
│           ├── domains/bug-fix/  # Bug Fix Dashboard
│           ├── components/       # Flow editor, panels, tabs
│           └── App.tsx
├── src/
│   └── llm/                      # LLM integration
│       └── models.py             # Model providers (used by bug_fix)
└── docs/
    └── evaluation-plan.md        # Self-evolution evaluation methodology
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Poetry

### Backend

```bash
cd ai-hedge-fund
poetry install
cp .env.example .env
# Edit .env with your API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, or DEEPSEEK_API_KEY)
```

### Frontend

```bash
cd app/frontend
npm install
npm run dev
```

### Run the Bug Fix Pipeline

```bash
# Fetch a bug and run the pipeline
cd app/backend
python -m domains.bug_fix.cli --jira-id PROJ-123

# Sync PR reviews
python -m domains.bug_fix.pr_sync --project AI --repo corevo --since 7d

# Start the web dashboard
cd app/frontend && npm run dev
# Visit http://localhost:5173/bug-fix
```

## Evaluation

See [docs/evaluation-plan.md](docs/evaluation-plan.md) for the quantitative evaluation methodology:

- **A/B/C/D control groups:** Cold start → Novice → Experienced → Veteran
- **Primary metrics:** First-fix rate, final-fix rate, iteration count
- **Secondary metrics:** Hypothesis accuracy, false-change rate, regression rate
- **Learning curve:** Tracking improvement over bug count

## Branches

| Branch | Purpose |
|--------|---------|
| `feature/digital-worker` | Active development |
| `baseline/self-evolving-v1` | Frozen baseline for A/B evaluation |

## License

MIT
