#!/usr/bin/env python3
"""Update an OBS text source from the latest row in a JSONL file."""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MAX_TAIL_BYTES = 1024 * 1024


@dataclass(frozen=True)
class LatestRecord:
    line: str
    data: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch a JSONL file and show the latest raw_text in an OBS text source."
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Path to the upstream .jsonl file.",
    )
    parser.add_argument(
        "--latest-glob",
        default="",
        help=(
            "Glob pattern for upstream .jsonl files. The newest matching file is "
            "selected at startup and re-selected while running."
        ),
    )
    parser.add_argument(
        "--input-name",
        default=os.getenv("OBS_INPUT_NAME", "当前查询"),
        help="OBS text source/input name. Defaults to OBS_INPUT_NAME or 当前查询.",
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
        "--field",
        default="raw_text",
        help="JSON field to display. Dot paths are supported, e.g. danmu.raw_text.",
    )
    parser.add_argument(
        "--prefix",
        default="当前查询：",
        help="Text prefix shown before the field value.",
    )
    parser.add_argument(
        "--wrap-width",
        default=0,
        type=int,
        help=(
            "Auto-wrap text at this display width. Chinese characters count as 2. "
            "Disabled by default."
        ),
    )
    parser.add_argument(
        "--max-lines",
        default=0,
        type=int,
        help="Maximum wrapped lines to show. 0 means unlimited.",
    )
    parser.add_argument(
        "--interval",
        default=0.3,
        type=float,
        help="Polling fallback interval in seconds. Defaults to 0.3.",
    )
    parser.add_argument(
        "--watch-mode",
        choices=("auto", "watchdog", "poll"),
        default="auto",
        help="Use filesystem events, polling, or auto fallback. Defaults to auto.",
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
        help="Maximum bytes to scan from the end of the file. Defaults to 1 MiB.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Read and update once, then exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the text that would be sent to OBS without connecting to OBS.",
    )
    args = parser.parse_args()
    if bool(args.file) == bool(args.latest_glob):
        parser.error("provide exactly one of --file or --latest-glob")
    return args


def read_latest_record(
    path: Path,
    *,
    encoding: str = "utf-8",
    max_tail_bytes: int = DEFAULT_MAX_TAIL_BYTES,
) -> LatestRecord | None:
    if not path.exists():
        return None

    size = path.stat().st_size
    if size == 0:
        return None

    start = max(0, size - max_tail_bytes)
    with path.open("rb") as file_obj:
        file_obj.seek(start)
        raw = file_obj.read()

    text = raw.decode(encoding, errors="replace")
    lines = text.splitlines()
    if start > 0 and lines:
        lines = lines[1:]

    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return LatestRecord(line=stripped, data=data)

    return None


def resolve_latest_path(pattern: str) -> Path | None:
    matches = [Path(path) for path in glob.glob(os.path.expanduser(pattern))]
    files = [path for path in matches if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: (path.stat().st_mtime_ns, str(path)))


def resolve_input_path(args: argparse.Namespace) -> Path | None:
    if args.latest_glob:
        return resolve_latest_path(args.latest_glob)
    return args.file


class ObsTextClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        password: str,
        input_name: str,
        dry_run: bool,
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

    def update_text(self, text: str) -> None:
        if self.dry_run:
            print(text, flush=True)
            return

        assert self._client is not None
        self._client.set_input_settings(
            self.input_name,
            {"text": text},
            True,
        )


def char_display_width(char: str) -> int:
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in ("F", "W"):
        return 2
    return 1


def wrap_display_text(text: str, width: int, max_lines: int = 0) -> str:
    if width <= 0:
        return text

    lines = []
    current = []
    current_width = 0
    for char in text:
        if char == "\n":
            lines.append("".join(current))
            current = []
            current_width = 0
            continue

        char_width = char_display_width(char)
        if current and current_width + char_width > width:
            lines.append("".join(current))
            current = [char]
            current_width = char_width
        else:
            current.append(char)
            current_width += char_width

        if max_lines > 0 and len(lines) >= max_lines:
            break

    if max_lines <= 0 or len(lines) < max_lines:
        lines.append("".join(current))

    if max_lines > 0 and len(lines) > max_lines:
        lines = lines[:max_lines]

    return "\n".join(line.rstrip() for line in lines).rstrip()


def format_record(
    record: LatestRecord,
    *,
    field: str,
    prefix: str,
    wrap_width: int,
    max_lines: int,
) -> str | None:
    value = get_field_value(record.data, field)
    if value is None:
        return None
    return wrap_display_text(f"{prefix}{value}", wrap_width, max_lines)


def get_field_value(data: dict[str, Any], field: str) -> Any:
    current: Any = data
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def run(args: argparse.Namespace) -> int:
    client = ObsTextClient(
        host=args.host,
        port=args.port,
        password=args.password,
        input_name=args.input_name,
        dry_run=args.dry_run,
    )

    last_record_key = None
    last_source_path = None
    last_missing_field_key = None

    def update_from_file() -> None:
        nonlocal last_record_key, last_source_path, last_missing_field_key
        source_path = resolve_input_path(args)
        if source_path is None:
            if args.dry_run:
                print(f"[wait] no file matches: {args.latest_glob}", flush=True)
            return
        if source_path != last_source_path:
            if args.latest_glob:
                print(f"[source] {source_path}", file=sys.stderr, flush=True)
            last_source_path = source_path

        record = read_latest_record(
            source_path,
            encoding=args.encoding,
            max_tail_bytes=args.max_tail_bytes,
        )
        if record:
            record_key = (str(source_path), record.line)
            if record_key == last_record_key:
                return
            text = format_record(
                record,
                field=args.field,
                prefix=args.prefix,
                wrap_width=args.wrap_width,
                max_lines=args.max_lines,
            )
            if text is None:
                if record_key != last_missing_field_key:
                    print(
                        f"[skip] field {args.field} not found in latest record",
                        file=sys.stderr,
                        flush=True,
                    )
                    last_missing_field_key = record_key
                last_record_key = record_key
                return
            client.update_text(text)
            last_record_key = record_key
            last_missing_field_key = None

    if args.once:
        try:
            update_from_file()
        except Exception as exc:
            print(f"Update failed: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.latest_glob and args.watch_mode != "watchdog":
        return run_with_polling(args, update_from_file)

    if args.watch_mode in ("auto", "watchdog"):
        try:
            return run_with_watchdog(args, update_from_file)
        except ImportError:
            if args.watch_mode == "watchdog":
                print(
                    "watchdog is not installed. Install dependencies with: "
                    "python3 -m pip install -r requirements.txt",
                    file=sys.stderr,
                )
                return 1
            print("watchdog is not installed; falling back to polling.", file=sys.stderr)

    return run_with_polling(args, update_from_file)


def run_with_polling(args: argparse.Namespace, update_from_file: Any) -> int:
    while True:
        try:
            update_from_file()
        except KeyboardInterrupt:
            print("\nStopped.", file=sys.stderr)
            return 0
        except Exception as exc:
            print(f"Update failed: {exc}", file=sys.stderr)

        time.sleep(max(args.interval, 0.05))


def run_with_watchdog(args: argparse.Namespace, update_from_file: Any) -> int:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    if args.latest_glob:
        print(
            "--latest-glob with --watch-mode watchdog is not supported; use --watch-mode poll.",
            file=sys.stderr,
        )
        return 1

    target_path = args.file.resolve()
    watch_dir = target_path.parent
    lock = threading.Lock()

    def safe_update() -> None:
        with lock:
            update_from_file()

    class JsonlChangeHandler(FileSystemEventHandler):
        def _matches(self, event: Any) -> bool:
            paths = [getattr(event, "src_path", None), getattr(event, "dest_path", None)]
            return any(path and Path(path).resolve() == target_path for path in paths)

        def on_created(self, event: Any) -> None:
            if self._matches(event):
                safe_update()

        def on_modified(self, event: Any) -> None:
            if self._matches(event):
                safe_update()

        def on_moved(self, event: Any) -> None:
            if self._matches(event):
                safe_update()

    observer = Observer()
    observer.schedule(JsonlChangeHandler(), str(watch_dir), recursive=False)
    observer.start()
    try:
        safe_update()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 0
    except Exception as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1
    finally:
        observer.stop()
        observer.join()


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
