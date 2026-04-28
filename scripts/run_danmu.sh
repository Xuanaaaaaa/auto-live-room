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

if [[ -n "${LIVE_ID:-}" ]]; then
  current_live_id="$(python3 - "$MAIN" <<'PY'
import re
import sys
text = open(sys.argv[1], encoding="utf-8").read()
match = re.search(r"live_id\s*=\s*['\"]([^'\"]+)['\"]", text)
print(match.group(1) if match else "")
PY
)"
  if [[ -n "$current_live_id" && "$current_live_id" != "$LIVE_ID" ]]; then
    echo "WARN: .env LIVE_ID=$LIVE_ID, but main.py currently hardcodes live_id=$current_live_id." >&2
    echo "      First-step scripts do not rewrite business code. Update main.py or wait for parameterized entrypoints." >&2
  fi
fi

cd "$DANMU_DIR"
echo "Starting danmu fetcher..."
echo "Watch for: [init] 结构化输出 (JSONL): output/<live_id>_<timestamp>.jsonl"
exec "$PY" "$MAIN"
