#!/usr/bin/env bash
set -euo pipefail

# Start the OBS media-source audio player on the host machine.
# This is intentionally separate from start_all.sh and the main pipeline.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_env

OBS_DIR="$ROOT_DIR/Obs_auto"
PY="$OBS_DIR/.venv/bin/python"
MAIN="$OBS_DIR/obs_audio_player.py"

require_executable "$PY" "Run ./scripts/bootstrap.sh first."
require_file "$MAIN"

cmd=("$PY" "$MAIN")

if [[ -n "${OBS_AUDIO_EVENTS_FILE:-}" ]]; then
  if [[ "$OBS_AUDIO_EVENTS_FILE" = /* ]]; then
    events_file="$OBS_AUDIO_EVENTS_FILE"
  else
    events_file="$ROOT_DIR/$OBS_AUDIO_EVENTS_FILE"
  fi
  cmd+=("--file" "$events_file")
else
  cmd+=("--latest-glob" "${OBS_AUDIO_EVENTS_GLOB:-$ROOT_DIR/链路监控/events/events_*.jsonl}")
fi

cmd+=("--input-name" "${OBS_AUDIO_INPUT_NAME:-岗位语音}")
cmd+=("--host" "${OBS_HOST:-localhost}")
cmd+=("--port" "${OBS_PORT:-4455}")
cmd+=("--path-mode" "${OBS_AUDIO_PATH_MODE:-auto}")

if flag_enabled "${OBS_AUDIO_FROM_START:-0}"; then
  cmd+=("--from-start")
fi

if flag_enabled "${OBS_AUDIO_DRY_RUN:-0}"; then
  cmd+=("--dry-run")
fi

if flag_enabled "${OBS_AUDIO_ONCE:-0}"; then
  cmd+=("--once")
fi

cd "$OBS_DIR"
echo "Starting OBS audio player..."
exec "${cmd[@]}"
