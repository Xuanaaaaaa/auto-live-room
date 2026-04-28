#!/usr/bin/env python3
"""Compatibility entrypoint for the live-room orchestrator.

The old command still works:
    python pipeline_monitor.py --danmu-jsonl ...

New code should call orchestrator.py directly. Monitoring is now handled by
monitor.py, which tails the event stream produced by orchestrator.py.
"""

from orchestrator import main


if __name__ == "__main__":
    raise SystemExit(main())
