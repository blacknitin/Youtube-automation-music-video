#!/usr/bin/env bash
# SongForge — dev helper: (re)install deps and start the server.
set -e
cd "$(dirname "$0")/.."

if [ ! -d backend/.venv ]; then
  echo "[1/2] Creating venv + installing deps…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

echo "[2/2] Starting SongForge on http://localhost:8000"
cd backend
DATA_DIR="${DATA_DIR:-$PWD/data}" .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
