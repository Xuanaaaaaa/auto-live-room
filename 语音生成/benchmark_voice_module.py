#!/usr/bin/env python3
"""Benchmark voice generation stages across two git versions.

The script loads one version from git (`git show <commit>:...`) and the current
workspace version from disk, then runs the same prepared job-search response
through the real LLM and TTS providers configured by the project `.env`.
API keys are never written to the JSON or HTML reports.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import statistics
import subprocess
import sys
import time
import types
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
VOICE_REL_PATH = "语音生成/job_narration_workflow.py"


def load_module_from_git(commit: str, module_name: str):
    code = subprocess.check_output(
        ["git", "show", f"{commit}:{VOICE_REL_PATH}"],
        cwd=ROOT,
        text=True,
    )
    module = types.ModuleType(module_name)
    module.__file__ = str(ROOT / VOICE_REL_PATH)
    sys.modules[module_name] = module
    exec(compile(code, module.__file__, "exec"), module.__dict__)
    return module


def load_module_from_path(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def now_ms() -> float:
    return time.perf_counter() * 1000


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = round((len(ordered) - 1) * q)
    return ordered[idx]


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    stage_names = [
        "load_input_ms",
        "pick_first_job_ms",
        "normalize_job_ms",
        "llm_narration_ms",
        "tts_synthesis_ms",
        "serialize_result_ms",
        "total_ms",
    ]
    summary: dict[str, Any] = {}
    for stage in stage_names:
        values = [float(run["timing_ms"][stage]) for run in runs]
        summary[stage] = {
            "n": len(values),
            "avg": statistics.mean(values),
            "p50": quantile(values, 0.50),
            "p90": quantile(values, 0.90),
            "max": max(values),
        }
    return summary


def config_namespace() -> SimpleNamespace:
    return SimpleNamespace(
        llm_api_key="",
        llm_base_url="",
        llm_model="",
        tts_api_key="",
        tts_app_id="",
        tts_http_url="",
        tts_resource_id="",
        tts_voice="",
        tts_format="",
        tts_sample_rate="",
    )


def run_real_voice_once(
    module,
    label: str,
    input_path: Path,
    audio_dir: Path,
    run_index: int,
    narration_mode: str,
) -> dict[str, Any]:
    t0 = now_ms()
    response_json = module.load_json_source(str(input_path))
    t1 = now_ms()
    first_job = module.pick_first_job(response_json)
    t2 = now_ms()
    job = module.normalize_job(first_job)
    t3 = now_ms()
    if narration_mode == "template":
        narration = module.generate_template_script(job)
    else:
        narration = module.generate_script_with_doubao(job, module.llm_config_from_env(config_namespace()))
    t4 = now_ms()
    audio_path = audio_dir / f"{label}_run{run_index}_{uuid.uuid4().hex[:8]}.mp3"
    module.synthesize_with_doubao_tts(
        narration.spoken_text,
        audio_path,
        module.tts_config_from_env(config_namespace()),
    )
    t5 = now_ms()
    result = {
        "job": module.asdict(job) | {"raw": job.raw},
        "narration": module.asdict(narration),
        "audio_path": str(audio_path),
    }
    json.dumps({"ok": True, **result}, ensure_ascii=False)
    t6 = now_ms()
    return {
        "label": label,
        "narration_mode": narration_mode,
        "run_index": run_index,
        "timing_ms": {
            "load_input_ms": t1 - t0,
            "pick_first_job_ms": t2 - t1,
            "normalize_job_ms": t3 - t2,
            "llm_narration_ms": t4 - t3,
            "tts_synthesis_ms": t5 - t4,
            "serialize_result_ms": t6 - t5,
            "total_ms": t6 - t0,
        },
        "narration": module.asdict(narration),
        "audio_path": str(audio_path),
        "audio_size_bytes": audio_path.stat().st_size,
    }


def benchmark_version(
    module,
    label: str,
    input_path: Path,
    audio_dir: Path,
    rounds: int,
    narration_mode: str = "llm",
) -> dict[str, Any]:
    runs = []
    for idx in range(1, rounds + 1):
        print(f"[benchmark] {label} run {idx}/{rounds}", flush=True)
        runs.append(run_real_voice_once(module, label, input_path, audio_dir, idx, narration_mode))
    return {
        "label": label,
        "narration_mode": narration_mode,
        "runs": runs,
        "summary": summarize_runs(runs),
    }


def write_html_report(report: dict[str, Any], output_path: Path) -> None:
    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    versions = report["versions"]
    benchmarks = report["benchmarks"]
    stage_labels = [
        ("load_input_ms", "加载输入"),
        ("pick_first_job_ms", "选择岗位"),
        ("normalize_job_ms", "字段归一化"),
        ("llm_narration_ms", "文案生成"),
        ("tts_synthesis_ms", "TTS 合成"),
        ("serialize_result_ms", "序列化输出"),
        ("total_ms", "总耗时"),
    ]

    timing_rows = []
    for stage_key, stage_name in stage_labels:
        cells = [f"<td>{esc(stage_name)}</td>"]
        for bench in benchmarks:
            stat = bench["summary"][stage_key]
            cells.append(
                "<td>"
                f"avg {stat['avg']:.1f} ms<br>"
                f"p50 {stat['p50']:.1f} ms<br>"
                f"p90 {stat['p90']:.1f} ms<br>"
                f"max {stat['max']:.1f} ms"
                "</td>"
            )
        timing_rows.append("<tr>" + "".join(cells) + "</tr>")

    timing_header = "".join(f"<th>{esc(bench['label'])}</th>" for bench in benchmarks)

    output_blocks = []
    for bench in benchmarks:
        first = bench["runs"][0]
        narration = first["narration"]
        output_blocks.append(
            "<section>"
            f"<h3>{esc(bench['label'])} sample output</h3>"
            f"<p><strong>mode:</strong> {esc(bench.get('narration_mode'))}</p>"
            f"<p><strong>source:</strong> {esc(narration.get('source'))}</p>"
            f"<p><strong>spoken_text:</strong> {esc(narration.get('spoken_text'))}</p>"
            f"<p><strong>title:</strong> {esc(narration.get('title'))}</p>"
            f"<p><strong>tags:</strong> {esc(narration.get('tags'))}</p>"
            f"<p><strong>risk_tips:</strong> {esc(narration.get('risk_tips'))}</p>"
            f"<p><strong>audio:</strong> {esc(first['audio_path'])} ({first['audio_size_bytes']} bytes)</p>"
            "</section>"
        )

    run_rows = []
    for bench in benchmarks:
        for run in bench["runs"]:
            timing = run["timing_ms"]
            run_rows.append(
                "<tr>"
                f"<td>{esc(bench['label'])}</td>"
                f"<td>{esc(bench.get('narration_mode'))}</td>"
                f"<td>{run['run_index']}</td>"
                f"<td>{timing['llm_narration_ms']:.1f}</td>"
                f"<td>{timing['tts_synthesis_ms']:.1f}</td>"
                f"<td>{timing['total_ms']:.1f}</td>"
                f"<td>{esc(run['audio_path'])}</td>"
                "</tr>"
            )

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>语音生成模块版本对比</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #202124; }}
    h1, h2, h3 {{ margin-bottom: 8px; }}
    .meta, .note {{ color: #5f6368; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0 28px; }}
    th, td {{ border: 1px solid #dadce0; padding: 10px; vertical-align: top; text-align: left; }}
    th {{ background: #f1f3f4; }}
    code {{ background: #f1f3f4; padding: 2px 4px; border-radius: 4px; }}
    section {{ border: 1px solid #dadce0; padding: 16px; margin: 16px 0; border-radius: 8px; }}
  </style>
</head>
<body>
  <h1>语音生成模块版本对比</h1>
  <p class="meta">生成时间：{esc(report['generated_at'])}</p>
  <p class="meta">测试输入：{esc(report['input_path'])}</p>
  <p class="meta">轮数：每组 {report['rounds']} 轮。LLM 组调用真实 LLM + 真实 TTS；template 组跳过 LLM，只调用真实 TTS。</p>

  <h2>版本</h2>
  <table>
    <thead><tr><th>版本</th><th>提交</th><th>说明</th></tr></thead>
    <tbody>
      <tr><td>baseline</td><td><code>{esc(versions['baseline_commit'])}</code></td><td>最开始基准版本，LLM 输出 JSON 后解析 spoken_text。</td></tr>
      <tr><td>current</td><td><code>{esc(versions['current_commit'])}</code></td><td>当前版本，LLM 输出纯文案，title/tags/risk_tips 由代码派生，模板为事实片段拼装。</td></tr>
    </tbody>
  </table>

  <h2>阶段耗时汇总</h2>
  <table>
    <thead><tr><th>阶段</th>{timing_header}</tr></thead>
    <tbody>
      {''.join(timing_rows)}
    </tbody>
  </table>

  <h2>单轮明细</h2>
  <table>
    <thead><tr><th>版本</th><th>模式</th><th>轮次</th><th>文案 ms</th><th>TTS ms</th><th>Total ms</th><th>音频文件</th></tr></thead>
    <tbody>
      {''.join(run_rows)}
    </tbody>
  </table>

  <h2>输出对比</h2>
  {''.join(output_blocks)}

  <p class="note">报告不包含任何 API key。音频文件位于被 .gitignore 忽略的 <code>链路监控/audio/</code> 下。</p>
</body>
</html>
"""
    output_path.write_text(html_text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--input", type=Path, default=ROOT / "语音生成/examples/sample_job_response.json")
    parser.add_argument("--output-html", type=Path, default=ROOT / "docs/语音生成模块版本对比.html")
    parser.add_argument("--output-json", type=Path, default=ROOT / "docs/语音生成模块版本对比.json")
    parser.add_argument("--audio-dir", type=Path, default=ROOT / "链路监控/audio/voice_benchmark")
    args = parser.parse_args(argv)

    args.audio_dir.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)

    baseline = load_module_from_git(args.baseline_commit, "voice_baseline")
    current = load_module_from_path(ROOT / VOICE_REL_PATH, "voice_current")
    current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "input_path": str(args.input),
        "rounds": args.rounds,
        "versions": {
            "baseline_commit": args.baseline_commit,
            "current_commit": current_commit,
        },
        "benchmarks": [
            benchmark_version(baseline, "baseline_llm", args.input, args.audio_dir, args.rounds, "llm"),
            benchmark_version(current, "current_llm", args.input, args.audio_dir, args.rounds, "llm"),
            benchmark_version(current, "current_template", args.input, args.audio_dir, args.rounds, "template"),
        ],
    }
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_html_report(report, args.output_html)
    print(json.dumps({"html": str(args.output_html), "json": str(args.output_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
