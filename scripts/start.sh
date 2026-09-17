#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT=$(pwd)

PORT="${TPS_PORT:-8771}"
HOST="${TPS_HOST:-127.0.0.1}"
PIDFILE="$ROOT/work/tps.pid"
LOGFILE="$ROOT/work/tps_http.log"

mkdir -p "$ROOT/work" "$ROOT/data" "$ROOT/output"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Already running (PID $(cat "$PIDFILE")) on http://$HOST:$PORT"
  exit 0
fi

if lsof -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "Port $PORT is in use by another process"
  exit 1
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Creating venv..."
  python3 -m venv "$ROOT/.venv"
fi
source "$ROOT/.venv/bin/activate"
pip install -q --disable-pip-version-check -r "$ROOT/requirements.txt"

AI_PROVIDER="${AI_PROVIDER:-openai}"
if [[ "$AI_PROVIDER" == "openai" && -z "${OPENAI_API_KEY:-}" ]]; then
  echo "error: OPENAI_API_KEY is not set for AI_PROVIDER=openai." >&2
  exit 1
fi
if [[ "$AI_PROVIDER" == "claude" ]] && ! command -v "${CLAUDE_COMMAND:-claude}" >/dev/null 2>&1; then
  echo "error: ${CLAUDE_COMMAND:-claude} is not in PATH for AI_PROVIDER=claude." >&2
  exit 1
fi

echo "Starting on http://$HOST:$PORT ..."
nohup uvicorn tps.app:app --host "$HOST" --port "$PORT" >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "PID $(cat "$PIDFILE") — log: $LOGFILE"
