#!/bin/bash
#
# AI Hedge Fund - Development Server
# One-click install dependencies and start the project
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              AI Hedge Fund - Development Server              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Check prerequisites ──────────────────────────────────────────────────────

echo -e "${YELLOW}[1/4] Checking prerequisites...${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] Python 3 is not installed. Please install Python 3.11+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "  ✓ Python ${PYTHON_VERSION}"

# Check Poetry
if ! command -v poetry &> /dev/null; then
    echo -e "${YELLOW}  ⚠ Poetry not found. Installing...${NC}"
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
fi
echo -e "  ✓ Poetry $(poetry --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo 'installed')"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}[ERROR] Node.js is not installed. Please install Node.js 18+${NC}"
    exit 1
fi
NODE_VERSION=$(node --version)
echo -e "  ✓ Node.js ${NODE_VERSION}"

# Check npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}[ERROR] npm is not installed.${NC}"
    exit 1
fi
echo -e "  ✓ npm $(npm --version)"

echo ""

# ── Install Python dependencies ──────────────────────────────────────────────

echo -e "${YELLOW}[2/4] Installing Python dependencies (Poetry)...${NC}"

if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}[ERROR] pyproject.toml not found in project root${NC}"
    exit 1
fi

poetry install --no-interaction 2>&1 | tail -5
echo -e "${GREEN}  ✓ Python dependencies installed${NC}"
echo ""

# ── Install frontend dependencies ────────────────────────────────────────────

echo -e "${YELLOW}[3/4] Installing frontend dependencies (npm)...${NC}"

if [ ! -d "app/frontend" ]; then
    echo -e "${RED}[ERROR] app/frontend directory not found${NC}"
    exit 1
fi

cd app/frontend
npm install --silent 2>&1 | tail -3
cd "$SCRIPT_DIR"
echo -e "${GREEN}  ✓ Frontend dependencies installed${NC}"
echo ""

# ── Check .env file ──────────────────────────────────────────────────────────

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo -e "${YELLOW}  ⚠ .env file not found. Copying from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}  ⚠ Please edit .env to add your API keys${NC}"
fi

# ── Start services ───────────────────────────────────────────────────────────

echo -e "${YELLOW}[4/4] Starting development servers...${NC}"
echo ""

# Create temp directory for logs
LOG_DIR=$(mktemp -d)
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null
    rm -rf "$LOG_DIR"
    echo -e "${GREEN}Done.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start backend
echo -e "${BLUE}Starting backend (FastAPI on http://localhost:8000)...${NC}"
cd app/backend
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000 > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# Wait a moment for backend to start
sleep 2

# Check if backend started successfully
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}[ERROR] Backend failed to start. Check the logs:${NC}"
    cat "$BACKEND_LOG"
    exit 1
fi
echo -e "${GREEN}  ✓ Backend started (PID: $BACKEND_PID)${NC}"

# Start frontend
echo -e "${BLUE}Starting frontend (Vite on http://localhost:5173)...${NC}"
cd app/frontend
npm run dev > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

# Wait a moment for frontend to start
sleep 2

# Check if frontend started successfully
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${RED}[ERROR] Frontend failed to start. Check the logs:${NC}"
    cat "$FRONTEND_LOG"
    cleanup
    exit 1
fi
echo -e "${GREEN}  ✓ Frontend started (PID: $FRONTEND_PID)${NC}"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Servers are running!                      ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Frontend:  http://localhost:5173                            ║${NC}"
echo -e "${GREEN}║  Backend:   http://localhost:8000                            ║${NC}"
echo -e "${GREEN}║  API Docs:  http://localhost:8000/docs                       ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Press Ctrl+C to stop all servers                            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Monitor logs in background
tail -f "$BACKEND_LOG" "$FRONTEND_LOG" 2>/dev/null &
TAIL_PID=$!

# Wait for any process to exit
wait -n $BACKEND_PID $FRONTEND_PID 2>/dev/null || true

# Cleanup
kill $TAIL_PID 2>/dev/null
cleanup
