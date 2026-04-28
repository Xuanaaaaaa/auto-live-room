#!/usr/bin/env bash
set -euo pipefail

# Start the read-only event monitor on the host machine.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_env

MONITOR_DIR="$ROOT_DIR/链路监控"
PY="$ROOT_DIR/语音生成/.venv/bin/python"
MAIN="$MONITOR_DIR/monitor.py"

require_executable "$PY" "Run ./scripts/bootstrap.sh first."
require_file "$MAIN"

events_glob="${MONITOR_EVENTS_GLOB:-$ROOT_DIR/链路监控/events/events_*.jsonl}"
cmd=("$PY" "$MAIN" "--events" "$events_glob")

if flag_enabled "${MONITOR_FROM_START:-0}"; then
  cmd+=("--from-start")
fi

cd "$MONITOR_DIR"
echo "Starting read-only event monitor..."
exec "${cmd[@]}"
