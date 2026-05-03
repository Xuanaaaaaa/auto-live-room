#!/usr/bin/env python3
"""Play completed TTS mp3 files in OBS via a media source.

This script is intentionally decoupled from the main pipeline. It only reads the
pipeline events JSONL and controls an existing OBS media source.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MEDIA_RESTART_ACTION = "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"
DEFAULT_MAX_TAIL_BYTES = 1024 * 1024


@dataclass(frozen=True)
class AudioEvent:
    trace_id: str
    audio_path: str
    stage: str
    raw: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch pipeline events JSONL and play completed TTS mp3 files in OBS."
    )
    parser.add_argument("--file", type=Path, help="Path to one events .jsonl file.")
    parser.add_argument(
        "--latest-glob",
        default="",
        help="Glob pattern for events .jsonl files. The newest file is followed.",
    )
    parser.add_argument(
        "--input-name",
        default=os.getenv("OBS_AUDIO_INPUT_NAME", "岗位语音"),
        help="OBS media source/input name. Defaults to OBS_AUDIO_INPUT_NAME or 岗位语音.",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("OBS_HOST", "localhost"),
        help="OBS WebSocket host. Defaults to OBS_HOST or localhost.",
    )
    parser.add_argument(
        "--port",
        default=int(os.getenv("OBS_PORT", "4455")),
        type=int,
        help="OBS WebSocket port. Defaults to OBS_PORT or 4455.",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("OBS_PASSWORD", ""),
        help="OBS WebSocket password. Defaults to OBS_PASSWORD or empty.",
    )
    parser.add_argument(
        "--path-mode",
        choices=("auto", "posix", "wsl-to-windows"),
        default=os.getenv("OBS_AUDIO_PATH_MODE", "auto"),
        help=(
            "How to convert audio paths before sending them to OBS. "
            "Use wsl-to-windows when OBS runs on Windows and this script runs in WSL."
        ),
    )
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Process existing events from the start. Defaults to only new events.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Find the latest playable audio event, play it once, then exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the audio file that would be played without connecting to OBS.",
    )
    parser.add_argument(
        "--interval",
        default=0.3,
        type=float,
        help="Polling interval in seconds. Defaults to 0.3.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="JSONL file encoding. Defaults to utf-8.",
    )
    parser.add_argument(
        "--max-tail-bytes",
        default=DEFAULT_MAX_TAIL_BYTES,
        type=int,
        help="Maximum bytes to scan for --once. Defaults to 1 MiB.",
    )
    args = parser.parse_args()
    if bool(args.file) == bool(args.latest_glob):
        parser.error("provide exactly one of --file or --latest-glob")
    return args


def is_wsl() -> bool:
    release = platform.release().lower()
    version = platform.version().lower()
    return "microsoft" in release or "microsoft" in version or bool(os.getenv("WSL_DISTRO_NAME"))


def convert_audio_path(path: str, mode: str) -> str:
    if mode == "auto":
        mode = "wsl-to-windows" if is_wsl() else "posix"

    if mode == "posix":
        return path

    # WSL exposes Windows drives as /mnt/c/Users/...; OBS on Windows needs C:\Users\...
    if path.startswith("/mnt/") and len(path) > 6 and path[6] == "/":
        drive = path[5].upper()
        rest = path[7:].replace("/", "\\")
        return f"{drive}:\\{rest}"

    return path


def resolve_latest_path(pattern: str) -> Path | None:
    matches = [Path(path) for path in glob.glob(os.path.expanduser(pattern))]
    files = [path for path in matches if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: (path.stat().st_mtime_ns, str(path)))


def extract_audio_event(data: dict[str, Any]) -> AudioEvent | None:
    stage = str(data.get("stage") or "")
    audio_path = data.get("audio_path")

    if not audio_path and isinstance(data.get("tts"), dict):
        audio_path = data["tts"].get("audio_path")

    if not audio_path:
        return None
    if stage not in ("completed", "synthesized", "voice_synthesized"):
        return None

    return AudioEvent(
        trace_id=str(data.get("trace_id") or audio_path),
        audio_path=str(audio_path),
        stage=stage,
        raw=data,
    )


def iter_events_from_lines(lines: list[str]) -> list[AudioEvent]:
    events: list[AudioEvent] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        event = extract_audio_event(data)
        if event is not None:
            events.append(event)
    return events


def latest_audio_event(
    path: Path,
    *,
    encoding: str = "utf-8",
    max_tail_bytes: int = DEFAULT_MAX_TAIL_BYTES,
) -> AudioEvent | None:
    if not path.exists() or path.stat().st_size == 0:
        return None

    size = path.stat().st_size
    start = max(0, size - max_tail_bytes)
    with path.open("rb") as file_obj:
        file_obj.seek(start)
        raw = file_obj.read()

    text = raw.decode(encoding, errors="replace")
    lines = text.splitlines()
    if start > 0 and lines:
        lines = lines[1:]

    for event in reversed(iter_events_from_lines(lines)):
        return event
    return None


class ObsMediaPlayer:
    def __init__(
        self,
        *,
        input_name: str,
        host: str,
        port: int,
        password: str,
        dry_run: bool = False,
    ) -> None:
        self.input_name = input_name
        self.dry_run = dry_run
        self._client = None

        if dry_run:
            return

        try:
            import obsws_python as obs
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency obsws-python. Install it with: "
                "python3 -m pip install -r requirements.txt"
            ) from exc

        self._client = obs.ReqClient(
            host=host,
            port=port,
            password=password,
            timeout=3,
        )

    def play(self, obs_path: str) -> None:
        if self.dry_run:
            print(f"[dry-run] play {obs_path}", flush=True)
            return

        assert self._client is not None
        self._client.set_input_settings(
            self.input_name,
            {
                "is_local_file": True,
                "local_file": obs_path,
            },
            True,
        )
        self._client.trigger_media_input_action(self.input_name, MEDIA_RESTART_ACTION)


class EventsFollower:
    def __init__(
        self,
        *,
        fixed_file: Path | None,
        latest_glob: str,
        encoding: str,
        from_start: bool,
    ) -> None:
        self.fixed_file = fixed_file
        self.latest_glob = latest_glob
        self.encoding = encoding
        self.from_start = from_start
        self.path: Path | None = None
        self.offset = 0
        self._buffer = ""

    def _resolve_path(self) -> Path | None:
        if self.fixed_file is not None:
            return self.fixed_file
        return resolve_latest_path(self.latest_glob)

    def read_new_events(self) -> list[AudioEvent]:
        path = self._resolve_path()
        if path is None or not path.exists():
            return []

        if self.path is None or path.resolve() != self.path.resolve():
            self.path = path
            self._buffer = ""
            self.offset = 0 if self.from_start else path.stat().st_size
            print(f"[watch] events file: {path}", flush=True)
            return []

        size = path.stat().st_size
        if size < self.offset:
            self.offset = 0
            self._buffer = ""
        if size == self.offset:
            return []

        with path.open("rb") as file_obj:
            file_obj.seek(self.offset)
            chunk = file_obj.read()
            self.offset = file_obj.tell()

        text = chunk.decode(self.encoding, errors="replace")
        combined = self._buffer + text
        if combined.endswith("\n"):
            lines = combined.splitlines()
            self._buffer = ""
        else:
            lines = combined.splitlines()
            self._buffer = lines.pop() if lines else combined

        return iter_events_from_lines(lines)


def run_once(args: argparse.Namespace, player: ObsMediaPlayer) -> int:
    path = args.file or resolve_latest_path(args.latest_glob)
    if path is None:
        print("ERROR: no events file found", file=sys.stderr)
        return 1

    event = latest_audio_event(
        path,
        encoding=args.encoding,
        max_tail_bytes=args.max_tail_bytes,
    )
    if event is None:
        print(f"ERROR: no playable audio event found in {path}", file=sys.stderr)
        return 1

    obs_path = convert_audio_path(event.audio_path, args.path_mode)
    print(f"[audio] trace={event.trace_id} stage={event.stage} path={obs_path}", flush=True)
    player.play(obs_path)
    return 0


def main() -> int:
    args = parse_args()
    player = ObsMediaPlayer(
        input_name=args.input_name,
        host=args.host,
        port=args.port,
        password=args.password,
        dry_run=args.dry_run,
    )

    if args.once:
        return run_once(args, player)

    follower = EventsFollower(
        fixed_file=args.file,
        latest_glob=args.latest_glob,
        encoding=args.encoding,
        from_start=args.from_start,
    )
    seen: set[tuple[str, str]] = set()
    print(f"[init] OBS media source: {args.input_name}", flush=True)
    print(f"[init] path mode: {args.path_mode}", flush=True)

    try:
        while True:
            for event in follower.read_new_events():
                key = (event.trace_id, event.audio_path)
                if key in seen:
                    continue
                seen.add(key)
                obs_path = convert_audio_path(event.audio_path, args.path_mode)
                print(
                    f"[audio] trace={event.trace_id} stage={event.stage} path={obs_path}",
                    flush=True,
                )
                try:
                    player.play(obs_path)
                except Exception as exc:
                    print(f"[WARN] failed to play audio: {type(exc).__name__}: {exc}", file=sys.stderr)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[shutdown] KeyboardInterrupt", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
