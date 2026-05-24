from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.database import SessionLocal
from app.services.mlops import MLOpsService
from app.services.retraining import RetrainingService, RetrainingServiceError
from app.tasks.retraining import fine_tune_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print retraining readiness and optionally dispatch fine-tuning."
    )
    parser.add_argument("--start", action="store_true", help="Dispatch a retraining job.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow a manual test job even when training_ready_cases is below N.",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=None,
        help="Optional temporary threshold for this manual start request.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db = SessionLocal()
    try:
        summary = MLOpsService(db).retraining_summary()
        print("Retraining summary")
        print(f"min_confirmed_samples: {summary['min_confirmed_samples']}")
        print(f"training_ready_cases: {summary['training_ready_cases']}")
        print(f"training_seed_count: {summary['training_seed_count']}")
        print(f"total_finetune_samples: {summary['total_finetune_samples']}")
        print(f"missing_confirmed_samples: {summary['missing_confirmed_samples']}")
        print(f"retrain_auto_start: {summary['retrain_auto_start']}")
        print(f"evaluation_set_available: {summary['evaluation_set_available']}")
        print(f"evaluation_set_sample_count: {summary['evaluation_set_sample_count']}")
        print(f"should_trigger_retraining: {summary['should_trigger_retraining']}")

        if not args.start:
            return

        service = RetrainingService(db)
        job = service.create_retraining_job(
            force=args.force,
            min_samples=args.min_samples,
            triggered_by=None,
        )
        fine_tune_model.delay(str(job.retraining_job_id))
        print("Retraining job dispatched")
        print(f"retraining_job_id: {job.retraining_job_id}")
        print(f"status: {job.status}")
        print(f"trigger_type: {job.trigger_type}")
        print(f"samples: {job.training_samples_count}/{job.min_required_samples}")
    except RetrainingServiceError as exc:
        raise SystemExit(f"Retraining smoke test failed: {exc.message}") from exc
    finally:
        db.close()


if __name__ == "__main__":
    main()
