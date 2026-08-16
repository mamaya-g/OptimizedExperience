#!/usr/bin/env python
"""Standalone poller: appends a timestamped snapshot of every attraction's
live status to a local CSV log -- the seed of a real, self-collected
reliability dataset over time, meant to eventually replace the hand-seeded
reliability_profile.yaml (see reliability.py and the plan's data notes).

Run once (e.g. via cron every few minutes):
    PYTHONPATH=src .venv/bin/python scripts/collect_status_log.py

Or keep it running in the foreground:
    PYTHONPATH=src .venv/bin/python scripts/collect_status_log.py --loop
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from optimized_experience.data.client import ThemeParksWikiSource
from optimized_experience.data.reliability import append_status_snapshot

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "status_log.csv"
DEFAULT_INTERVAL_SECONDS = 120  # matches themeparks.wiki's live refresh cadence


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append a live Disneyland attraction status snapshot to a local CSV log."
    )
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument(
        "--loop", action="store_true", help="Keep polling every --interval-seconds instead of running once."
    )
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args()

    source = ThemeParksWikiSource()
    try:
        while True:
            live = source.get_live()
            append_status_snapshot(args.log_path, live.liveData)
            print(f"Logged {len(live.liveData)} entity statuses to {args.log_path}")
            if not args.loop:
                break
            time.sleep(args.interval_seconds)
    finally:
        source.close()


if __name__ == "__main__":
    main()
