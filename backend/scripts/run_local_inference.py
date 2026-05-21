from __future__ import annotations

import argparse
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.ml.inference import run_inference  # noqa: E402
from app.ml.model_loader import (  # noqa: E402
    ARCHITECTURE_MOBILENET_V3_SMALL,
    MODEL_SOURCE_DEMO,
    MODEL_SOURCE_LOCAL,
    load_model,
)
from app.ml.types import (  # noqa: E402
    PREDICTION_MODE_MULTICLASS,
    PREDICTION_MODE_MULTILABEL,
)

DEMO_WARNING = "Using demo model. Results are not clinically meaningful."
TASK_TYPE_MULTI_CLASS = "multi_class"
TASK_TYPE_MULTI_LABEL = "multi_label"
TASK_TYPE_TO_PREDICTION_MODE = {
    TASK_TYPE_MULTI_CLASS: PREDICTION_MODE_MULTICLASS,
    TASK_TYPE_MULTI_LABEL: PREDICTION_MODE_MULTILABEL,
}
TASK_TYPE_ALIASES = {
    "multi_class": TASK_TYPE_MULTI_CLASS,
    "multiclass": TASK_TYPE_MULTI_CLASS,
    "multi-class": TASK_TYPE_MULTI_CLASS,
    "single_label": TASK_TYPE_MULTI_CLASS,
    "single-label": TASK_TYPE_MULTI_CLASS,
    "single_label_multi_class": TASK_TYPE_MULTI_CLASS,
    "multi_label": TASK_TYPE_MULTI_LABEL,
    "multilabel": TASK_TYPE_MULTI_LABEL,
    "multi-label": TASK_TYPE_MULTI_LABEL,
}


def normalize_task_type(task_type: str) -> str:
    normalized = task_type.strip().lower()
    try:
        return TASK_TYPE_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(
            "Unsupported task type "
            f"'{task_type}'. Use multi_class or multi_label."
        ) from exc


def ensure_task_type_matches_model(task_type: str, prediction_mode: str) -> None:
    expected_prediction_mode = TASK_TYPE_TO_PREDICTION_MODE[normalize_task_type(task_type)]
    if prediction_mode != expected_prediction_mode:
        raise ValueError(
            f"Requested task type '{task_type}' expects prediction mode "
            f"'{expected_prediction_mode}', but loaded model uses '{prediction_mode}'."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local chest X-ray inference.")
    parser.add_argument("--image", required=True, help="Path to an image file.")
    parser.add_argument(
        "--model-path",
        default=None,
        help="Optional local model checkpoint path. If omitted, demo mode is used.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=settings.model_threshold,
        help="Positive threshold for multi-label models. Ignored for multi-class.",
    )
    parser.add_argument(
        "--architecture",
        default=settings.model_architecture,
        help=(
            "Local model architecture. Use mobilenet_v3_small for the Kaggle "
            "single-label multi-class checkpoint."
        ),
    )
    parser.add_argument(
        "--device",
        default=settings.model_device,
        help="Torch device, default cpu.",
    )
    parser.add_argument(
        "--task-type",
        default=None,
        help=(
            "Optional task type guard: multi_class for the Kaggle single-label "
            "MobileNetV3 model, or multi_label for legacy demo experiments."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not image_path.is_file():
        raise ValueError(f"Image path is not a file: {image_path}")

    if args.model_path is None:
        print(DEMO_WARNING)
        loaded_model = load_model(
            model_source=MODEL_SOURCE_DEMO,
            device=args.device,
            allow_demo_model=True,
        )
    else:
        loaded_model = load_model(
            model_source=MODEL_SOURCE_LOCAL,
            model_path=args.model_path,
            architecture=args.architecture or ARCHITECTURE_MOBILENET_V3_SMALL,
            device=args.device,
        )

    if args.task_type is not None:
        ensure_task_type_matches_model(args.task_type, loaded_model.prediction_mode)

    outputs = run_inference(
        image_path,
        loaded_model=loaded_model,
        threshold=args.threshold,
    )

    for output in outputs:
        print(
            f"{output.label_name}: "
            f"probability={output.probability:.6f}, "
            f"predicted_positive={output.predicted_positive}"
        )


if __name__ == "__main__":
    main()
