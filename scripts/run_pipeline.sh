#!/usr/bin/env bash
set -euo pipefail

# Start the live-room orchestrator on the host machine.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_env

MONITOR_DIR="$ROOT_DIR/链路监控"
PY="$ROOT_DIR/语音生成/.venv/bin/python"
MAIN="$MONITOR_DIR/orchestrator.py"

require_executable "$PY" "Run ./scripts/bootstrap.sh first."
require_file "$MAIN"

live_id="${LIVE_ID:-*}"
default_danmu_glob="$ROOT_DIR/弹幕提取/DouyinLiveWebFetcher/output/${live_id}_*.jsonl"

if [[ -n "${DANMU_JSONL:-}" ]]; then
  danmu_jsonl="$DANMU_JSONL"
else
  danmu_glob="${DANMU_JSONL_GLOB:-$default_danmu_glob}"
  if ! danmu_jsonl="$(latest_match "$danmu_glob")"; then
    echo "ERROR: no JSONL file matches: $danmu_glob" >&2
    echo "Start the danmu fetcher first, or set DANMU_JSONL to a fixed output file." >&2
    exit 1
  fi
fi

cmd=("$PY" "$MAIN" "--danmu-jsonl" "$danmu_jsonl")

if flag_enabled "${PIPELINE_DRY_RUN:-0}"; then
  cmd+=("--dry-run")
else
  if [[ -z "${AIBZ_TOKEN:-}" ]]; then
    echo "ERROR: AIBZ_TOKEN is empty. Put the token without Bearer prefix in .env." >&2
    echo "For offline testing, set PIPELINE_DRY_RUN=1." >&2
    exit 1
  fi
fi

if flag_enabled "${PIPELINE_FROM_START:-0}"; then
  cmd+=("--from-start")
fi

if flag_enabled "${PIPELINE_NO_TTS:-0}"; then
  cmd+=("--no-tts")
fi

if [[ -n "${TRACES_OUT:-}" ]]; then
  cmd+=("--traces-out" "$TRACES_OUT")
fi

if [[ -n "${EVENTS_OUT:-}" ]]; then
  cmd+=("--events-out" "$EVENTS_OUT")
fi

audio_dir="${AUDIO_DIR:-$ROOT_DIR/链路监控/audio}"
cmd+=("--audio-dir" "$audio_dir")

cd "$MONITOR_DIR"
echo "Starting orchestrator..."
echo "Danmu JSONL: $danmu_jsonl"
exec "${cmd[@]}"
