from __future__ import annotations

import argparse
import sys
import time

from api.services.pricing_kb_import_admin import run_next_job


def main() -> None:
    parser = argparse.ArgumentParser(description="QMind PostgreSQL-backed pricing knowledge import worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    while True:
        try:
            job_id = run_next_job()
        except Exception as exc:
            if args.once:
                raise
            print(f"[pricing-kb-worker] job failed: {exc}", file=sys.stderr, flush=True)
            time.sleep(max(0.25, args.poll_seconds))
            continue
        if args.once:
            return
        if job_id is None:
            time.sleep(max(0.25, args.poll_seconds))


if __name__ == "__main__":
    main()
