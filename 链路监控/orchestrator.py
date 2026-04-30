#!/usr/bin/env python3
"""
直播间查岗端到端链路编排器.

链路:  弹幕命中  ->  小程序API搜索  ->  豆包LLM生成解说  ->  TTS合成音频
每条 trace 一个 uuid:
  - events/ 下写阶段事件流, 供 monitor.py 实时观察
  - traces/ 下写终态 JSONL, 供复盘和 stats.py 统计
中间过程实时打印到 stdout.

启动:
    python orchestrator.py \\
        --danmu-jsonl /path/to/弹幕提取/.../output/{live_id}_{ts}.jsonl \\
        --access-token <aibz_token>          # 或 export AIBZ_TOKEN

可选:
    --from-start    从 jsonl 开头消费, 默认仅读新追加行
    --no-tts        跳过 TTS 合成, 只跑文案
    --traces-out    自定义 trace 输出路径
    --events-out    自定义事件流输出路径
    --audio-dir     自定义音频输出目录
    --dry-run       不连任何真实 API, 用模板文案 + 跳过 TTS, 验证链路结构
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Generator, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "小程序API提取岗位信息"))
sys.path.insert(0, str(ROOT / "语音生成"))

from aibz_job_search import search_jobs_from_payload, JobSearchError  # noqa: E402
from job_narration_workflow import (  # noqa: E402
    DoubaoLLMConfig,
    DoubaoTTSConfig,
    WorkflowError,
    generate_script_with_doubao,
    generate_template_script,
    llm_config_from_env,
    normalize_job,
    synthesize_with_doubao_tts,
    tts_config_from_env,
)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_ms() -> float:
    return time.monotonic() * 1000


def _section_duration_ms(trace: Dict[str, Any], section: str) -> int:
    value = trace.get(section)
    if not isinstance(value, dict):
        return 0
    duration = value.get("duration_ms")
    return int(duration) if isinstance(duration, (int, float)) else 0


def _build_timing(trace: Dict[str, Any]) -> Dict[str, int]:
    search_ms = _section_duration_ms(trace, "search")
    narration_ms = _section_duration_ms(trace, "narration")
    tts_ms = _section_duration_ms(trace, "tts")
    voice_total_ms = narration_ms + tts_ms
    return {
        "search_ms": search_ms,
        "narration_ms": narration_ms,
        "tts_ms": tts_ms,
        "voice_total_ms": voice_total_ms,
        "end_to_end_ms": search_ms + voice_total_ms,
    }


def tail_jsonl(path: Path, from_start: bool = False) -> Generator[Dict[str, Any], None, None]:
    """tail -F 一个 jsonl, yield 每行解析后的 dict. 文件不存在时阻塞等待."""
    while not path.exists():
        print(f"[wait] danmu jsonl not yet: {path}")
        time.sleep(2)
    with open(path, "r", encoding="utf-8") as f:
        if not from_start:
            f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[skip-bad-line] {exc}: {line[:80]}", file=sys.stderr)


class TraceWriter:
    """终态 trace 写到 jsonl, 行缓冲, 一条 trace 一行."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, trace: Dict[str, Any]) -> None:
        self._fp.write(json.dumps(trace, ensure_ascii=False) + "\n")

    def close(self) -> None:
        if self._fp and not self._fp.closed:
            self._fp.close()


class EventWriter:
    """阶段事件写到 jsonl, 供监控器实时 tail."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, event: Dict[str, Any]) -> None:
        self._fp.write(json.dumps(event, ensure_ascii=False) + "\n")

    def close(self) -> None:
        if self._fp and not self._fp.closed:
            self._fp.close()


@dataclass
class OrchestratorConfig:
    access_token: str
    llm_config: Optional[DoubaoLLMConfig]
    tts_config: Optional[DoubaoTTSConfig]
    audio_dir: Path
    enable_tts: bool = True
    narration_mode: str = "llm"
    dry_run: bool = False
    page_size: int = 10


class Orchestrator:
    """单进程串行执行链路, 每条弹幕产出一条 trace."""

    def __init__(self, config: OrchestratorConfig, event_writer: Optional[EventWriter] = None):
        self.cfg = config
        self.event_writer = event_writer
        self.cfg.audio_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {
            "total": 0,
            "completed": 0,
            "failed_search": 0,
            "failed_narration": 0,
            "failed_tts": 0,
        }

    def handle(self, danmu_record: Dict[str, Any]) -> Dict[str, Any]:
        trace_id = uuid.uuid4().hex
        short = trace_id[:8]
        trace: Dict[str, Any] = {
            "trace_id": trace_id,
            "stage": "received",
            "ts_received": _now_iso(),
            "ts_searched": None,
            "ts_narrated": None,
            "ts_synthesized": None,
            "ts_completed": None,
            "danmu": _slim_danmu(danmu_record),
            "search": None,
            "narration": None,
            "tts": None,
            "timing": None,
            "error": None,
        }
        self.stats["total"] += 1
        print(
            f"[{short}] received: user={trace['danmu']['user_name']!r} "
            f"keyword={trace['danmu']['keyword']!r} city={trace['danmu']['city']!r} "
            f"raw={trace['danmu']['raw_text']!r}"
        )
        self._emit_event(trace, "received")

        first_job = self._step_search(trace, short)
        if first_job is None:
            self._emit_event(trace, trace["stage"], section="search")
            return trace

        narration_text = self._step_narration(trace, first_job, short)
        if narration_text is None:
            self._emit_event(trace, trace["stage"], section="narration")
            return trace

        if self.cfg.enable_tts:
            if not self._step_tts(trace, narration_text, short):
                self._emit_event(trace, trace["stage"], section="tts")
                return trace

        trace["stage"] = "completed"
        trace["ts_completed"] = _now_iso()
        trace["timing"] = _build_timing(trace)
        self.stats["completed"] += 1
        audio = trace["tts"]["audio_path"] if trace["tts"] else "(skipped)"
        print(
            f"[{short}] completed: audio={audio} "
            f"voice={trace['timing']['voice_total_ms']}ms "
            f"total={trace['timing']['end_to_end_ms']}ms"
        )
        self._emit_event(trace, "completed")
        return trace

    def _step_search(self, trace: Dict[str, Any], short: str) -> Optional[Dict[str, Any]]:
        t0 = _now_ms()
        payload = trace["danmu"].get("query_payload") or {}
        try:
            if self.cfg.dry_run:
                res = _dry_run_search_response()
            else:
                res = search_jobs_from_payload(
                    payload,
                    access_token=self.cfg.access_token,
                    page=1,
                    page_size=self.cfg.page_size,
                )
        except JobSearchError as exc:
            self._mark_failed(
                trace, "failed_search",
                f"JobSearchError code={exc.code}: {exc.msg}",
                "search", t0,
            )
            print(f"[{short}] FAILED search: {trace['error']}")
            return None
        except Exception as exc:
            self._mark_failed(
                trace, "failed_search",
                f"{type(exc).__name__}: {exc}",
                "search", t0,
            )
            print(f"[{short}] FAILED search: {trace['error']}")
            return None

        data = res.get("data") or []
        first = data[0] if data else None
        trace["search"] = {
            "ok": True,
            "count": res.get("count", 0),
            "returned": len(data),
            "first_job": (
                {
                    "id": first.get("id"),
                    "name": first.get("name"),
                    "company_name": first.get("company_name"),
                    "city": first.get("city"),
                }
                if first
                else None
            ),
            "duration_ms": int(_now_ms() - t0),
            "error": None,
        }
        trace["ts_searched"] = _now_iso()
        if first is None:
            self._mark_failed(
                trace, "failed_search",
                "search returned 0 jobs",
                "search", t0, mark_search=False,
            )
            print(f"[{short}] FAILED search: count=0")
            return None
        trace["stage"] = "searched"
        print(
            f"[{short}] searched: count={trace['search']['count']} "
            f"first={first.get('name')!r}@{first.get('company_name')!r} "
            f"({trace['search']['duration_ms']}ms)"
        )
        self._emit_event(trace, "searched", section="search")
        return first

    def _step_narration(
        self, trace: Dict[str, Any], first_job: Dict[str, Any], short: str
    ) -> Optional[str]:
        t0 = _now_ms()
        try:
            job = normalize_job(first_job)
            if self.cfg.dry_run or self.cfg.narration_mode == "template" or self.cfg.llm_config is None:
                narration = generate_template_script(job)
            else:
                narration = generate_script_with_doubao(job, self.cfg.llm_config)
        except WorkflowError as exc:
            self._mark_failed(
                trace, "failed_narration",
                f"WorkflowError: {exc}",
                "narration", t0,
            )
            print(f"[{short}] FAILED narration: {trace['error']}")
            return None
        except Exception as exc:
            self._mark_failed(
                trace, "failed_narration",
                f"{type(exc).__name__}: {exc}",
                "narration", t0,
            )
            print(f"[{short}] FAILED narration: {trace['error']}")
            return None

        trace["narration"] = {
            "ok": True,
            "spoken_text": narration.spoken_text,
            "title": narration.title,
            "tags": narration.tags,
            "risk_tips": narration.risk_tips,
            "source": narration.source,
            "duration_level": narration.duration_level,
            "duration_ms": int(_now_ms() - t0),
            "error": None,
        }
        trace["ts_narrated"] = _now_iso()
        trace["stage"] = "narrated"
        preview = narration.spoken_text[:60].replace("\n", " ")
        print(
            f"[{short}] narrated [{narration.source}]: {preview}... "
            f"({trace['narration']['duration_ms']}ms)"
        )
        self._emit_event(trace, "narrated", section="narration")
        return narration.spoken_text

    def _step_tts(self, trace: Dict[str, Any], spoken: str, short: str) -> bool:
        t0 = _now_ms()
        out_path = self.cfg.audio_dir / f"trace_{trace['trace_id']}.mp3"
        try:
            synthesize_with_doubao_tts(spoken, out_path, self.cfg.tts_config)
        except WorkflowError as exc:
            self._mark_failed(
                trace, "failed_tts",
                f"WorkflowError: {exc}",
                "tts", t0,
            )
            print(f"[{short}] FAILED tts: {trace['error']}")
            return False
        except Exception as exc:
            self._mark_failed(
                trace, "failed_tts",
                f"{type(exc).__name__}: {exc}",
                "tts", t0,
            )
            print(f"[{short}] FAILED tts: {trace['error']}")
            return False

        trace["tts"] = {
            "ok": True,
            "audio_path": str(out_path),
            "audio_size_bytes": out_path.stat().st_size,
            "duration_ms": int(_now_ms() - t0),
            "error": None,
        }
        trace["ts_synthesized"] = _now_iso()
        trace["stage"] = "synthesized"
        print(
            f"[{short}] synthesized: {out_path.name} "
            f"({trace['tts']['audio_size_bytes']}B, {trace['tts']['duration_ms']}ms)"
        )
        self._emit_event(trace, "synthesized", section="tts")
        return True

    def _mark_failed(
        self,
        trace: Dict[str, Any],
        stage: str,
        error: str,
        section: str,
        t0: float,
        mark_search: bool = True,
    ) -> None:
        trace["stage"] = stage
        trace["error"] = error
        if section == "search" and mark_search:
            trace["search"] = {
                "ok": False,
                "duration_ms": int(_now_ms() - t0),
                "error": error,
            }
        elif section == "narration":
            trace["narration"] = {
                "ok": False,
                "duration_ms": int(_now_ms() - t0),
                "error": error,
            }
        elif section == "tts":
            trace["tts"] = {
                "ok": False,
                "duration_ms": int(_now_ms() - t0),
                "error": error,
            }
        self.stats[stage] = self.stats.get(stage, 0) + 1

    def _emit_event(
        self,
        trace: Dict[str, Any],
        stage: str,
        section: Optional[str] = None,
    ) -> None:
        if self.event_writer is None:
            return
        event: Dict[str, Any] = {
            "type": "stage",
            "ts": _now_iso(),
            "trace_id": trace.get("trace_id"),
            "stage": stage,
            "error": trace.get("error"),
        }
        if stage == "received":
            event["danmu"] = trace.get("danmu")
        if section and isinstance(trace.get(section), dict):
            event[section] = trace.get(section)
        if stage == "completed":
            event["audio_path"] = (
                trace.get("tts", {}).get("audio_path")
                if isinstance(trace.get("tts"), dict)
                else None
            )
            event["timing"] = trace.get("timing") or _build_timing(trace)
        self.event_writer.write(event)


_DRY_SAMPLE_PATH = ROOT / "语音生成" / "examples" / "sample_job_response.json"


def _dry_run_search_response() -> Dict[str, Any]:
    """dry-run 不连真实接口, 直接读语音生成项目的 sample_job_response.json."""
    if _DRY_SAMPLE_PATH.exists():
        with open(_DRY_SAMPLE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "code": 200, "msg": "dry-run", "count": 1,
        "data": [{
            "id": 1, "name": "演示岗位", "company_name": "演示公司",
            "city": "北京", "company_type_key": "民营",
            "company_title_key": "中小企业",
            "start_time": "2026-04-28", "end_time": "招满即止",
            "recommendedMessage": "演示推荐语",
        }],
    }


_DANMU_KEEP = (
    "ts", "live_id", "user_id", "user_name",
    "keyword", "city", "industry", "salary", "experience", "education",
    "source", "raw_text", "query_payload",
)


def _slim_danmu(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: record.get(k) for k in _DANMU_KEEP}


def _build_configs(args: argparse.Namespace):
    """构造 LLM/TTS 配置. dry-run 模式下完全跳过, 不要求 API key."""
    if args.dry_run:
        return None, None
    fake = SimpleNamespace(
        llm_api_key=args.llm_api_key, llm_base_url=args.llm_base_url, llm_model=args.llm_model,
        tts_api_key=args.tts_api_key, tts_app_id=args.tts_app_id, tts_http_url=args.tts_http_url,
        tts_resource_id=args.tts_resource_id, tts_voice=args.tts_voice,
        tts_format=args.tts_format, tts_sample_rate=args.tts_sample_rate,
    )
    llm = None if args.narration_mode == "template" else llm_config_from_env(fake)
    tts = None if args.no_tts else tts_config_from_env(fake)
    return llm, tts


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--danmu-jsonl", required=True, help="弹幕端落盘的 jsonl 路径")
    p.add_argument("--access-token", default="", help="aibz access_token, 或环境变量 AIBZ_TOKEN")
    p.add_argument("--traces-out", default="", help="trace 输出 jsonl 路径")
    p.add_argument("--events-out", default="", help="event 输出 jsonl 路径")
    p.add_argument("--audio-dir", default="", help="TTS 音频输出目录")
    p.add_argument("--from-start", action="store_true", help="从弹幕 jsonl 开头消费")
    p.add_argument("--no-tts", action="store_true", help="跳过 TTS 合成")
    p.add_argument(
        "--narration-mode",
        choices=("llm", "template"),
        default="llm",
        help="解说文案生成方式: llm=豆包LLM, template=本地模板",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="不连任何真实 API, 用模板文案 + 跳过 TTS, 验证链路结构")
    p.add_argument("--page-size", type=int, default=10, help="search_jobs page_size")
    # 透传给豆包配置, 默认全空 -> 走 env / 内置默认值
    p.add_argument("--llm-api-key", default="")
    p.add_argument("--llm-base-url", default="")
    p.add_argument("--llm-model", default="")
    p.add_argument("--tts-api-key", default="")
    p.add_argument("--tts-app-id", default="")
    p.add_argument("--tts-http-url", default="")
    p.add_argument("--tts-resource-id", default="")
    p.add_argument("--tts-voice", default="")
    p.add_argument("--tts-format", default="")
    p.add_argument("--tts-sample-rate", default="")
    args = p.parse_args(argv)

    if not args.dry_run:
        token = args.access_token or os.getenv("AIBZ_TOKEN", "")
        if not token:
            print("ERROR: 没有 access_token, 用 --access-token 或 export AIBZ_TOKEN", file=sys.stderr)
            return 2
    else:
        token = "DRY_RUN"

    here = Path(__file__).resolve().parent
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    traces_path = Path(args.traces_out) if args.traces_out else (here / "traces" / f"traces_{ts}.jsonl")
    events_path = Path(args.events_out) if args.events_out else (here / "events" / f"events_{ts}.jsonl")
    audio_dir = Path(args.audio_dir) if args.audio_dir else (here / "audio")
    danmu_path = Path(args.danmu_jsonl)

    llm_config, tts_config = _build_configs(args)
    enable_tts = (not args.no_tts) and (not args.dry_run)

    cfg = OrchestratorConfig(
        access_token=token,
        llm_config=llm_config,
        tts_config=tts_config,
        audio_dir=audio_dir,
        enable_tts=enable_tts,
        narration_mode=args.narration_mode,
        dry_run=args.dry_run,
        page_size=args.page_size,
    )
    event_writer = EventWriter(events_path)
    orch = Orchestrator(cfg, event_writer=event_writer)
    writer = TraceWriter(traces_path)

    print(f"[init] danmu jsonl: {danmu_path}")
    print(f"[init] events:      {events_path}")
    print(f"[init] traces:      {traces_path}")
    print(f"[init] audio dir:   {audio_dir} (tts={'on' if enable_tts else 'off'})")
    print(f"[init] narration:   {args.narration_mode}")
    print(f"[init] dry_run:     {args.dry_run}")

    try:
        for record in tail_jsonl(danmu_path, from_start=args.from_start):
            try:
                trace = orch.handle(record)
            except Exception as exc:
                trace = {
                    "trace_id": uuid.uuid4().hex,
                    "stage": "failed_unknown",
                    "ts_received": _now_iso(),
                    "danmu": _slim_danmu(record),
                    "error": f"orchestrator crash: {type(exc).__name__}: {exc}",
                }
                print(f"[crash] {trace['error']}", file=sys.stderr)
                event_writer.write({
                    "type": "stage",
                    "ts": _now_iso(),
                    "trace_id": trace["trace_id"],
                    "stage": "failed_unknown",
                    "danmu": trace["danmu"],
                    "error": trace["error"],
                })
            writer.write(trace)
    except KeyboardInterrupt:
        print("\n[shutdown] KeyboardInterrupt")
    finally:
        writer.close()
        event_writer.close()
        s = orch.stats
        print("\n=== stats ===")
        print(f"  total:    {s['total']}")
        print(f"  ok:       {s['completed']}")
        print(
            f"  failed:   search={s['failed_search']} "
            f"narration={s['failed_narration']} tts={s['failed_tts']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
