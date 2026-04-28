#!/usr/bin/env python3
"""
实时观察 orchestrator.py 写出的 events JSONL。

monitor.py 只读事件流, 不调用 aibz、LLM 或 TTS。

用法:
    python monitor.py
    python monitor.py --events "events/events_*.jsonl" --from-start
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _resolve_latest(pattern: str) -> Optional[Path]:
    paths = [Path(p) for p in glob.glob(pattern) if Path(p).is_file()]
    if not paths:
        return None
    return max(paths, key=lambda p: (p.stat().st_mtime_ns, str(p)))


def _read_new_events(path: Path, offset: int) -> tuple[int, list[Dict[str, Any]]]:
    if not path.exists():
        return offset, []
    size = path.stat().st_size
    if offset > size:
        offset = 0
    events = []
    with path.open("r", encoding="utf-8") as f:
        f.seek(offset)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        offset = f.tell()
    return offset, events


def _format_event(event: Dict[str, Any]) -> str:
    trace_id = str(event.get("trace_id") or "")
    short = trace_id[:8] or "--------"
    stage = event.get("stage") or "unknown"
    error = event.get("error")

    if stage == "received":
        danmu = event.get("danmu") if isinstance(event.get("danmu"), dict) else {}
        return (
            f"[{short}] received "
            f"keyword={danmu.get('keyword')!r} city={danmu.get('city')!r} "
            f"raw={danmu.get('raw_text')!r}"
        )
    if stage == "searched":
        search = event.get("search") if isinstance(event.get("search"), dict) else {}
        first = search.get("first_job") if isinstance(search.get("first_job"), dict) else {}
        return (
            f"[{short}] searched count={search.get('count')} "
            f"first={first.get('name')!r} ({search.get('duration_ms')}ms)"
        )
    if stage == "narrated":
        narration = event.get("narration") if isinstance(event.get("narration"), dict) else {}
        text = str(narration.get("spoken_text") or "").replace("\n", " ")[:50]
        return f"[{short}] narrated source={narration.get('source')!r} text={text!r}"
    if stage == "synthesized":
        tts = event.get("tts") if isinstance(event.get("tts"), dict) else {}
        return (
            f"[{short}] synthesized size={tts.get('audio_size_bytes')} "
            f"({tts.get('duration_ms')}ms)"
        )
    if stage == "completed":
        return f"[{short}] completed audio={event.get('audio_path') or '(skipped)'}"
    if str(stage).startswith("failed"):
        return f"[{short}] {stage} error={error}"
    return f"[{short}] {stage} error={error}"


def _print_summary(stage_counts: Counter, error_counts: Counter) -> None:
    total = sum(stage_counts.values())
    print("\n=== event stats ===")
    print(f"  total events: {total}")
    for stage, count in stage_counts.most_common():
        print(f"  {stage:18s} {count:6d}")
    if error_counts:
        print("  top errors:")
        for error, count in error_counts.most_common(5):
            print(f"    [{count}x] {error}")


def _iter_sources(pattern: str, from_start: bool, interval: float) -> Iterable[Dict[str, Any]]:
    current_path: Optional[Path] = None
    offset = 0
    while True:
        path = _resolve_latest(pattern) if any(c in pattern for c in "*?[") else Path(pattern)
        if path is None:
            print(f"[wait] no event file matches: {pattern}", file=sys.stderr)
            time.sleep(interval)
            continue
        if path != current_path:
            current_path = path
            offset = 0 if from_start else path.stat().st_size
            print(f"[source] {path}", file=sys.stderr)

        offset, events = _read_new_events(path, offset)
        for event in events:
            yield event
        time.sleep(interval)


def main(argv: Optional[list[str]] = None) -> int:
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--events",
        default=str(here / "events" / "events_*.jsonl"),
        help="events jsonl 路径或通配, 默认 events/events_*.jsonl",
    )
    p.add_argument("--from-start", action="store_true", help="从事件文件开头读取")
    p.add_argument("--interval", type=float, default=0.5, help="轮询间隔秒数")
    args = p.parse_args(argv)

    stage_counts: Counter = Counter()
    error_counts: Counter = Counter()
    try:
        for event in _iter_sources(args.events, args.from_start, max(args.interval, 0.1)):
            stage = str(event.get("stage") or "unknown")
            stage_counts[stage] += 1
            if event.get("error"):
                error_counts[str(event["error"])[:200]] += 1
            print(_format_event(event), flush=True)
    except KeyboardInterrupt:
        print("\n[shutdown] KeyboardInterrupt", file=sys.stderr)
    finally:
        _print_summary(stage_counts, error_counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
