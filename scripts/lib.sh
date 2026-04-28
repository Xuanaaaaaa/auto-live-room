#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

load_env() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    local line key value
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line#"${line%%[![:space:]]*}"}"
      line="${line%"${line##*[![:space:]]}"}"
      [[ -z "$line" || "$line" == \#* ]] && continue
      [[ "$line" == export\ * ]] && line="${line#export }"
      [[ "$line" != *=* ]] && continue
      key="${line%%=*}"
      value="${line#*=}"
      key="${key%"${key##*[![:space:]]}"}"
      value="${value#"${value%%[![:space:]]*}"}"
      value="${value%"${value##*[![:space:]]}"}"
      if [[ "$value" == \"*\" && "$value" == *\" ]]; then
        value="${value:1:${#value}-2}"
      elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
        value="${value:1:${#value}-2}"
      fi
      if [[ -n "$key" && -z "${!key+x}" ]]; then
        export "$key=$value"
      fi
    done < "$ROOT_DIR/.env"
  fi
}

require_file() {
  local path="$1"
  local hint="${2:-}"
  if [[ ! -f "$path" ]]; then
    echo "ERROR: file not found: $path" >&2
    if [[ -n "$hint" ]]; then
      echo "$hint" >&2
    fi
    exit 1
  fi
}

require_executable() {
  local path="$1"
  local hint="${2:-}"
  if [[ ! -x "$path" ]]; then
    echo "ERROR: executable not found: $path" >&2
    if [[ -n "$hint" ]]; then
      echo "$hint" >&2
    fi
    exit 1
  fi
}

latest_match() {
  local pattern="$1"
  python3 - "$pattern" <<'PY'
import glob
import os
import sys
from pathlib import Path

pattern = os.path.expanduser(sys.argv[1])
files = [Path(path) for path in glob.glob(pattern) if Path(path).is_file()]
if not files:
    raise SystemExit(1)
latest = max(files, key=lambda path: (path.stat().st_mtime_ns, str(path)))
print(latest)
PY
}

flag_enabled() {
  case "${1:-0}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

ensure_runtime_dirs() {
  mkdir -p "${LOG_DIR:-$ROOT_DIR/logs}" "${RUN_DIR:-$ROOT_DIR/.run}"
}

pid_is_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pid_file_is_running() {
  local path="$1"
  [[ -f "$path" ]] || return 1
  local pid
  pid="$(cat "$path" 2>/dev/null || true)"
  pid_is_running "$pid"
}

wait_for_file_newer_than() {
  local pattern="$1"
  local previous="${2:-}"
  local timeout_seconds="${3:-30}"
  local label="${4:-file}"
  python3 - "$pattern" "$previous" "$timeout_seconds" "$label" <<'PY'
import glob
import os
import sys
import time
from pathlib import Path

pattern, previous, timeout_s, label = sys.argv[1:5]
deadline = time.time() + float(timeout_s)
previous_path = Path(previous) if previous else None

while True:
    files = [Path(path) for path in glob.glob(os.path.expanduser(pattern)) if Path(path).is_file()]
    if files:
        latest = max(files, key=lambda path: (path.stat().st_mtime_ns, str(path)))
        if previous_path is None or latest.resolve() != previous_path.resolve():
            print(latest)
            raise SystemExit(0)
    if time.time() >= deadline:
        print(f"ERROR: timed out waiting for {label}: {pattern}", file=sys.stderr)
        raise SystemExit(1)
    time.sleep(0.5)
PY
}
