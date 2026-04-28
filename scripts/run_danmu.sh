#!/usr/bin/env bash
set -euo pipefail

# Start the Douyin danmu fetcher on the host machine.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_env

DANMU_DIR="$ROOT_DIR/弹幕提取/DouyinLiveWebFetcher"
PY="$DANMU_DIR/venv/bin/python"
MAIN="$DANMU_DIR/main.py"

require_executable "$PY" "Run ./scripts/bootstrap.sh first."
require_file "$MAIN"

if [[ -z "${LIVE_ID:-}" ]]; then
  echo "ERROR: LIVE_ID is empty. Set LIVE_ID in project .env." >&2
  exit 1
fi

cd "$DANMU_DIR"
echo "Starting danmu fetcher..."
echo "LIVE_ID: $LIVE_ID"
echo "Watch for: [init] 结构化输出 (JSONL): output/${LIVE_ID}_<timestamp>.jsonl"
exec "$PY" "$MAIN"
