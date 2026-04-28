#!/usr/bin/env bash
set -euo pipefail

# Tail logs written by scripts/start_all.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_env

LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
RUN_DIR="${RUN_DIR:-$ROOT_DIR/.run}"
ensure_runtime_dirs

usage() {
  cat <<EOF
Usage: ./scripts/logs.sh <danmu|pipeline|monitor|all>
EOF
}

target="${1:-}"
case "$target" in
  danmu|pipeline|monitor)
    touch "$LOG_DIR/$target.log"
    exec tail -f "$LOG_DIR/$target.log"
    ;;
  all)
    touch "$LOG_DIR/danmu.log" "$LOG_DIR/pipeline.log" "$LOG_DIR/monitor.log"
    exec tail -f "$LOG_DIR/danmu.log" "$LOG_DIR/pipeline.log" "$LOG_DIR/monitor.log"
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
