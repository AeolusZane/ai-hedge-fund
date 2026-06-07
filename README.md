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
- **Visual workflow editor:** React Flow-based canvas for building and monitoring pipelines
- **Real-time dashboard:** Live pipeline visualization with node status updates
- **Automated scheduling:** Cron-based daily bug fetching + PR sync

## Project Structure

```
ai-hedge-fund/
├── app/
│   ├── backend/                  # FastAPI backend
│   │   ├── domains/
│   │   │   └── bug_fix/          # Self-evolving bug fix agent
│   │   │       ├── executor.py              # Workflow execution engine
│   │   │       ├── analyze_agent.py         # Bug analysis with LLM
│   │   │       ├── patch_agent.py           # Code patch generation
│   │   │       ├── test_agent.py            # Test execution
│   │   │       ├── pr_agent.py              # PR creation
│   │   │       ├── post_fix_agent.py        # Experience extraction
│   │   │       ├── bitbucket_client.py      # Bitbucket API client
│   │   │       ├── experience_store.py      # Bug pattern storage
│   │   │       ├── code_understanding_store.py  # Code cache
│   │   │       ├── pr_embedding/            # PR review vector store
│   │   │       └── pr_sync.py               # PR review sync
│   │   ├── core/
│   │   │   ├── executors/        # Base executor framework
│   │   │   └── models/           # Database models
│   │   ├── routes/               # API routes
│   │   ├── database/             # SQLite + migrations
│   │   ├── repositories/         # Data access layer
│   │   └── main.py               # FastAPI app entry
│   └── frontend/                 # React + Vite frontend
│       ├── src/
│       │   ├── domains/bug-fix/  # Bug Fix Dashboard components
│       │   ├── components/       # Flow editor, panels, tabs
│       │   ├── contexts/         # React contexts (flow, layout, tabs)
│       │   ├── nodes/            # Custom React Flow node types
│       │   └── App.tsx
│       └── dist/                 # Built frontend (served by backend)
├── requirements.txt              # Python dependencies
├── test_execution.py             # Workflow execution tests
└── .env                          # Environment configuration
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend development)

### Backend Setup

```bash
cd ai-hedge-fund

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys:
# - OPENAI_API_KEY or ANTHROPIC_API_KEY or DEEPSEEK_API_KEY (for LLM)
# - JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN (for Jira integration)
# - BITBUCKET_URL, BITBUCKET_USERNAME, BITBUCKET_PASSWORD (for Bitbucket)
```

### Frontend Setup (Development)

```bash
cd app/frontend
npm install
npm run dev
# Visit http://localhost:5173
```

### Frontend Build (Production)

```bash
cd app/frontend
npm run build
# Output: dist/ (served by backend at /)
```

### Run the Backend

```bash
cd ai-hedge-fund
source venv/bin/activate
uvicorn app.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run the Bug Fix Pipeline

**Via API:**
```bash
# Start a workflow run
curl -X POST http://localhost:8000/api/bug-fix/runs \
  -H "Content-Type: application/json" \
  -d '{
    "jira_issue": "PROJ-123",
    "project_key": "PROJ",
    "graph_nodes": [...],
    "graph_edges": [...]
  }'

# Stream progress via SSE
curl http://localhost:8000/api/bug-fix/runs/{run_id}/stream
```

**Via CLI:**
```bash
cd app/backend
python -m domains.bug_fix.cli --jira-id PROJ-123
```

**Sync PR Reviews:**
```bash
python -m domains.bug_fix.pr_sync --project AI --repo corevo --since 7d
```

### Run Tests

```bash
cd ai-hedge-fund
source venv/bin/activate
python test_execution.py
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | One of LLM keys |
| `ANTHROPIC_API_KEY` | Anthropic API key | One of LLM keys |
| `DEEPSEEK_API_KEY` | DeepSeek API key | One of LLM keys |
| `JIRA_BASE_URL` | Jira instance URL | For Jira integration |
| `JIRA_EMAIL` | Jira user email | For Jira integration |
| `JIRA_API_TOKEN` | Jira API token | For Jira integration |
| `BITBUCKET_URL` | Bitbucket server URL | For Bitbucket integration |
| `BITBUCKET_USERNAME` | Bitbucket username | For Bitbucket integration |
| `BITBUCKET_PASSWORD` | Bitbucket password/PAT | For Bitbucket integration |
| `DATABASE_URL` | SQLite database path | Optional (default: `./data/app.db`) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/bug-fix/runs` | POST | Start a new workflow run |
| `/api/bug-fix/runs/{id}` | GET | Get run status |
| `/api/bug-fix/runs/{id}/stream` | GET | SSE stream for progress |
| `/api/bug-fix/runs/{id}/cancel` | POST | Cancel a running workflow |
| `/api/bug-fix/experiences` | GET | List stored experiences |
| `/api/bug-fix/pr-sync` | POST | Trigger PR review sync |
| `/api/flows` | GET/POST | Manage workflow definitions |

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
