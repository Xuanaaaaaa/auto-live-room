#!/usr/bin/env bash
set -euo pipefail

# Prepare all host-side Python virtual environments used by the current project.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

echo "Project root: $ROOT_DIR"
python3 --version

setup_venv() {
  local name="$1"
  local dir="$2"
  local venv="$3"
  local requirements="$4"

  echo
  echo "==> $name"
  cd "$dir"
  if [[ ! -d "$venv" ]]; then
    python3 -m venv "$venv"
  fi
  "$venv/bin/python" -m pip install --upgrade pip
  "$venv/bin/python" -m pip install -r "$requirements"
}

setup_venv \
  "弹幕提取" \
  "$ROOT_DIR/弹幕提取/DouyinLiveWebFetcher" \
  "venv" \
  "requirements.txt"

setup_venv \
  "语音生成 + 链路监控" \
  "$ROOT_DIR/语音生成" \
  ".venv" \
  "requirements.txt"

setup_venv \
  "OBS 文本更新" \
  "$ROOT_DIR/Obs_auto" \
  ".venv" \
  "requirements.txt"

echo
echo "Bootstrap complete."
echo "Next:"
echo "  cp .env.example .env"
echo "  edit .env"
echo "  ./scripts/run_danmu.sh"
echo "  ./scripts/run_pipeline.sh"
echo "  ./scripts/run_monitor.sh"
echo "  ./scripts/run_obs_text.sh"
