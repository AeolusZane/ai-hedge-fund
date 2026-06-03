#!/bin/bash
set -e

echo "=== AI Hedge Fund Setup ==="

# 1. Python deps
if [ ! -d "venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv venv
fi
source venv/bin/activate
echo "Installing Python deps..."
pip install -q -r requirements.txt

# 2. Frontend
cd app/frontend
if [ ! -d "node_modules" ]; then
  echo "Installing frontend deps..."
  npm install
fi
echo "Building frontend..."
npm run build
cd ../..

# 3. Env
if [ ! -f ".env" ]; then
  echo "Copying .env.example to .env"
  cp .env.example .env
  echo "⚠️  Edit .env and add your API keys"
  exit 1
fi

# 4. Start
echo ""
echo "=== Starting backend ==="
echo "Backend: http://localhost:8080"
echo "Mobile Dashboard: http://localhost:8080/bug-fix"
echo ""
python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8080 --reload
