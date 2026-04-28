#!/usr/bin/env bash
set -euo pipefail

# Stop services started by scripts/start_all.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_env

LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
RUN_DIR="${RUN_DIR:-$ROOT_DIR/.run}"
ensure_runtime_dirs

stop_service() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"
  if [[ ! -f "$pid_file" ]]; then
    echo "$name      stopped"
    return
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if pid_is_running "$pid"; then
    echo "$name      stopping pid=$pid"
    kill "$pid" 2>/dev/null || true
    local deadline=$((SECONDS + 10))
    while pid_is_running "$pid" && (( SECONDS < deadline )); do
      sleep 0.2
    done
    if pid_is_running "$pid"; then
      echo "$name      still running pid=$pid; sending SIGKILL"
      kill -9 "$pid" 2>/dev/null || true
    fi
  else
    echo "$name      stale pid=$pid"
  fi
  rm -f "$pid_file"
}

stop_service monitor
stop_service pipeline
stop_service danmu
