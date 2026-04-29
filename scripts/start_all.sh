#!/usr/bin/env bash
set -euo pipefail

# Start the host-side live-room pipeline in the background.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_env

LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
RUN_DIR="${RUN_DIR:-$ROOT_DIR/.run}"
STARTUP_WAIT_SECONDS="${STARTUP_WAIT_SECONDS:-30}"

ensure_runtime_dirs

require_live_id() {
  prompt_live_id
  echo "[config] LIVE_ID=$LIVE_ID"
}

service_pid_file() {
  echo "$RUN_DIR/$1.pid"
}

ensure_not_running() {
  local name="$1"
  local pid_file
  pid_file="$(service_pid_file "$name")"
  if pid_file_is_running "$pid_file"; then
    echo "ERROR: $name is already running pid=$(cat "$pid_file"). Run ./scripts/status.sh or ./scripts/stop_all.sh." >&2
    exit 1
  fi
}

start_service() {
  local name="$1"
  shift
  local log_file="$LOG_DIR/$name.log"
  local pid_file
  pid_file="$(service_pid_file "$name")"

  : > "$log_file"
  echo "[start] $name -> $log_file"
  python3 - "$pid_file" "$ROOT_DIR" "$log_file" "$@" <<'PY'
import subprocess
import sys
from pathlib import Path

pid_file, cwd, log_file, *cmd = sys.argv[1:]
log = open(log_file, "ab", buffering=0)
proc = subprocess.Popen(
    cmd,
    cwd=cwd,
    stdin=subprocess.DEVNULL,
    stdout=log,
    stderr=subprocess.STDOUT,
    close_fds=True,
    start_new_session=True,
)
Path(pid_file).write_text(f"{proc.pid}\n", encoding="utf-8")
PY
  local pid
  pid="$(cat "$pid_file")"
  echo "[pid] $name pid=$pid"
}

require_live_id

for service in danmu pipeline monitor; do
  ensure_not_running "$service"
done

danmu_glob="$ROOT_DIR/弹幕提取/DouyinLiveWebFetcher/output/${LIVE_ID}_*.jsonl"
previous_danmu_jsonl=""
if previous_danmu_jsonl="$(latest_match "$danmu_glob" 2>/dev/null)"; then
  :
else
  previous_danmu_jsonl=""
fi

start_service danmu "$SCRIPT_DIR/run_danmu.sh"

echo "[wait] danmu jsonl: $danmu_glob"
danmu_jsonl="$(wait_for_file_newer_than "$danmu_glob" "$previous_danmu_jsonl" "$STARTUP_WAIT_SECONDS" "danmu jsonl")"
echo "[ready] danmu jsonl: $danmu_jsonl"

ts="$(date +%Y%m%d_%H%M%S)"
events_out="$ROOT_DIR/链路监控/events/events_${ts}.jsonl"
traces_out="$ROOT_DIR/链路监控/traces/traces_${ts}.jsonl"

start_service pipeline env \
  DANMU_JSONL="$danmu_jsonl" \
  EVENTS_OUT="$events_out" \
  TRACES_OUT="$traces_out" \
  "$SCRIPT_DIR/run_pipeline.sh"

echo "[wait] events file: $events_out"
wait_for_file_newer_than "$events_out" "" "$STARTUP_WAIT_SECONDS" "events file" >/dev/null
echo "[ready] events file: $events_out"

start_service monitor env \
  MONITOR_EVENTS_GLOB="$events_out" \
  "$SCRIPT_DIR/run_monitor.sh"

cat <<EOF

All services started.

Logs:
  ./scripts/logs.sh danmu
  ./scripts/logs.sh pipeline
  ./scripts/logs.sh monitor

Status:
  ./scripts/status.sh

Stop:
  ./scripts/stop_all.sh
EOF
