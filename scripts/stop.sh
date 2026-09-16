#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
PORT="${TPS_PORT:-8771}"
PIDFILE="work/tps.pid"

stopped=false

if [[ -f "$PIDFILE" ]]; then
  PID=$(cat "$PIDFILE")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Stopped (PID $PID)"
    stopped=true
  else
    echo "Process $PID already gone"
  fi
  rm -f "$PIDFILE"
fi

# Fallback: kill whatever is listening on the port
PIDS=$(lsof -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
if [[ -n "$PIDS" ]]; then
  echo "$PIDS" | xargs kill 2>/dev/null || true
  echo "Killed orphan process(es) on port $PORT"
  stopped=true
fi

if ! $stopped; then
  echo "Not running."
fi
