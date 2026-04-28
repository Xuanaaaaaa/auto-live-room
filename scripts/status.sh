#!/usr/bin/env bash
set -euo pipefail

# Show background service status.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_env

LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
RUN_DIR="${RUN_DIR:-$ROOT_DIR/.run}"
ensure_runtime_dirs

show_service() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"
  local log_file="$LOG_DIR/$name.log"
  if [[ ! -f "$pid_file" ]]; then
    printf "%-10s stopped log=%s\n" "$name" "$log_file"
    return
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if pid_is_running "$pid"; then
    printf "%-10s running pid=%s log=%s\n" "$name" "$pid" "$log_file"
  else
    printf "%-10s stale pid=%s log=%s\n" "$name" "${pid:-?}" "$log_file"
  fi
}

show_service danmu
show_service pipeline
show_service monitor
