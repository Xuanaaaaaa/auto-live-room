#!/usr/bin/python
# coding:utf-8

# @FileName:    main.py
# @Time:        2024/1/2 22:27
# @Author:      bubu
# @Project:     douyinLiveWebFetcher

import argparse
import os
from pathlib import Path

from liveMan import DouyinLiveWebFetcher


def load_project_env():
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args():
    parser = argparse.ArgumentParser(description="Start Douyin live danmu fetcher.")
    parser.add_argument(
        "--live-id",
        default=os.getenv("LIVE_ID", ""),
        help="Douyin live room id. Defaults to LIVE_ID from project .env.",
    )
    return parser.parse_args()


if __name__ == '__main__':
    load_project_env()
    args = parse_args()
    live_id = args.live_id.strip()
    if not live_id:
        raise SystemExit("Missing LIVE_ID. Set LIVE_ID in project .env or pass --live-id.")
    print(f"[init] LIVE_ID: {live_id}")
    room = DouyinLiveWebFetcher(live_id)
    # room.get_room_status() # 失效
    room.start()
