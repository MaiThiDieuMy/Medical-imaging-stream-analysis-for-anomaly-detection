from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import SessionLocal
from app.ml.evaluation_set import get_evaluation_set_status
from app.ml.finetune_dataset import build_finetune_dataset, load_training_seed_samples
from app.ml.retraining_dataset import RETRAIN_CLASS_ORDER
from app.services.retraining import RetrainingService


def _count_by_class(samples: list[object]) -> dict[str, int]:
    counts = {class_name: 0 for class_name in RETRAIN_CLASS_ORDER}
    for sample in samples:
        class_name = getattr(sample, "class_name", None)
        if class_name in counts:
            counts[class_name] += 1
    return counts


def _print_counts(title: str, counts: dict[str, int]) -> None:
    print(title)
    for class_name in RETRAIN_CLASS_ORDER:
        print(f"  {class_name}: {counts.get(class_name, 0)}")


def main() -> None:
    db = SessionLocal()
    try:
        service = RetrainingService(db)
        confirmed_items = service.get_training_ready_sample_items()
        finetune_summary = build_finetune_dataset(confirmed_items)
        seed_samples = load_training_seed_samples()
        evaluation_status = get_evaluation_set_status()
        threshold = settings.retrain_min_confirmed_samples
        threshold_met = finetune_summary.confirmed_count >= threshold

        print("Training data inspection")
        print(f"TRAINING_SEED_DIR: {settings.training_seed_dir}")
        print(f"EVALUATION_SET_DIR: {settings.evaluation_set_dir}")
        print(f"RETRAIN_INCLUDE_TRAINING_SEED: {settings.retrain_include_training_seed}")
        print(f"RETRAIN_SEED_MAX_PER_CLASS: {settings.retrain_seed_max_per_class}")
        print(f"RETRAIN_MIN_CONFIRMED_SAMPLES: {threshold}")
        print()
        _print_counts("Seed counts per class", _count_by_class(seed_samples))
        print()
        _print_counts("Evaluation counts per class", evaluation_status.class_counts)
        print()
        print(f"confirmed/corrected DB training-ready count: {finetune_summary.confirmed_count}")
        print(f"seed_count: {finetune_summary.seed_count}")
        print(f"total_finetune_samples: {finetune_summary.total_train_count}")
        print(f"threshold_met_by_confirmed_cases_only: {threshold_met}")
        if evaluation_status.warning:
            print(f"evaluation_warning: {evaluation_status.warning}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
