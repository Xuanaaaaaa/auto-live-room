#!/usr/bin/env bash
set -euo pipefail

# Start the OBS text-source updater on the host machine.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_env

OBS_DIR="$ROOT_DIR/Obs_auto"
PY="$OBS_DIR/.venv/bin/python"
MAIN="$OBS_DIR/obs_jsonl_text_updater.py"

require_executable "$PY" "Run ./scripts/bootstrap.sh first."
require_file "$MAIN"

cmd=("$PY" "$MAIN")
live_id="${LIVE_ID:-*}"
default_obs_glob="$ROOT_DIR/弹幕提取/DouyinLiveWebFetcher/output/${live_id}_*.jsonl"

if [[ -n "${OBS_FILE:-}" ]]; then
  cmd+=("--file" "$OBS_FILE")
else
  cmd+=("--latest-glob" "${OBS_LATEST_GLOB:-$default_obs_glob}")
fi

cmd+=("--input-name" "${OBS_INPUT_NAME:-当前查询}")
cmd+=("--host" "${OBS_HOST:-localhost}")
cmd+=("--port" "${OBS_PORT:-4455}")
cmd+=("--field" "${OBS_FIELD:-raw_text}")
cmd+=("--wrap-width" "${OBS_WRAP_WIDTH:-0}")
cmd+=("--max-lines" "${OBS_MAX_LINES:-0}")
cmd+=("--watch-mode" "${OBS_WATCH_MODE:-poll}")

if flag_enabled "${OBS_DRY_RUN:-0}"; then
  cmd+=("--dry-run")
fi

if flag_enabled "${OBS_ONCE:-0}"; then
  cmd+=("--once")
fi

cd "$OBS_DIR"
echo "Starting OBS text updater..."
exec "${cmd[@]}"
