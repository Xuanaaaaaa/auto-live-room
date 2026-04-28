#!/usr/bin/env python3
"""
读 traces*.jsonl 出统计:
  - 总数 / 各 stage 分布 / 成功率
  - search/narration/tts 阶段耗时分位数 (p50/p90/p99)
  - 失败原因 top 10

用法:
    python stats.py traces/traces_20260428_103000.jsonl
    python stats.py "traces/*.jsonl"        # 通配, 注意加引号
    cat traces/foo.jsonl | python stats.py -
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _iter_traces(sources: Iterable[str]) -> Iterable[Dict[str, Any]]:
    for src in sources:
        if src == "-":
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
            continue
        paths = sorted(glob.glob(src)) if any(c in src for c in "*?[") else [src]
        if not paths:
            print(f"[warn] no match for {src}", file=sys.stderr)
        for p in paths:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue


def _quantile(xs: List[int], q: float) -> Optional[int]:
    if not xs:
        return None
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[k]


def _summarize(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(traces)
    stage_counter = Counter(t.get("stage", "unknown") for t in traces)

    durations = {"search": [], "narration": [], "tts": []}
    error_counter: Counter = Counter()
    for t in traces:
        for sect in ("search", "narration", "tts"):
            data = t.get(sect)
            if isinstance(data, dict) and isinstance(data.get("duration_ms"), int):
                durations[sect].append(data["duration_ms"])
        err = t.get("error")
        if err:
            error_counter[_normalize_error(err)] += 1

    return {
        "total": total,
        "stage_counts": dict(stage_counter.most_common()),
        "completed_rate": (
            stage_counter.get("completed", 0) / total if total else 0.0
        ),
        "duration_ms": {
            sect: {
                "n": len(xs),
                "p50": _quantile(xs, 0.50),
                "p90": _quantile(xs, 0.90),
                "p99": _quantile(xs, 0.99),
                "max": max(xs) if xs else None,
            }
            for sect, xs in durations.items()
        },
        "top_errors": error_counter.most_common(10),
    }


def _normalize_error(err: str) -> str:
    """折叠掉错误里的可变细节 (uuid/path/数字), 让相似错误聚合."""
    import re

    e = re.sub(r"[a-f0-9]{32}", "<hex32>", err)
    e = re.sub(r"\d{4,}", "<num>", e)
    e = e[:200]
    return e


def _print_report(summary: Dict[str, Any]) -> None:
    print(f"total traces: {summary['total']}")
    print(f"completed rate: {summary['completed_rate']:.1%}")
    print()
    print("stage distribution:")
    for stage, n in summary["stage_counts"].items():
        pct = n / summary["total"] if summary["total"] else 0
        print(f"  {stage:20s} {n:6d}  ({pct:.1%})")
    print()
    print("duration (ms):")
    print(f"  {'stage':12s} {'n':>6s} {'p50':>8s} {'p90':>8s} {'p99':>8s} {'max':>8s}")
    for sect, d in summary["duration_ms"].items():
        if not d["n"]:
            continue
        print(
            f"  {sect:12s} {d['n']:6d} "
            f"{d['p50']:>8} {d['p90']:>8} {d['p99']:>8} {d['max']:>8}"
        )
    print()
    if summary["top_errors"]:
        print("top errors:")
        for err, n in summary["top_errors"]:
            print(f"  [{n}x] {err}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sources", nargs="+", help="trace jsonl 路径或通配, '-' 读 stdin")
    p.add_argument("--json", action="store_true", help="只输出 JSON")
    args = p.parse_args(argv)

    traces = list(_iter_traces(args.sources))
    summary = _summarize(traces)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_report(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
