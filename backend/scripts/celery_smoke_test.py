from __future__ import annotations

import argparse
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tasks.health import worker_health  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch a Celery worker health task.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for the worker response.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    async_result = worker_health.delay()
    print(f"Dispatched worker health task: {async_result.id}")
    result = async_result.get(timeout=args.timeout)
    print(result)


if __name__ == "__main__":
    main()
