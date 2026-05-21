from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image
import torch
from torch import nn

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.ml.inference import run_inference  # noqa: E402
from app.ml.labels import DEMO_LABELS  # noqa: E402
from app.ml.model_loader import (  # noqa: E402
    ARCHITECTURE_MOBILENET_V3_SMALL,
    MODEL_SOURCE_LOCAL,
    load_model,
    normalize_architecture_name,
)
from app.ml.types import PREDICTION_MODE_MULTICLASS  # noqa: E402

DEFAULT_MODEL_PATH = Path("artifacts/models/best_model.pth")
TASK_TYPE_MULTI_CLASS = "multi_class"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the local Kaggle MobileNetV3-Small checkpoint."
    )
    parser.add_argument(
        "--model-path",
        default=settings.model_weights_path or str(DEFAULT_MODEL_PATH),
        help="Path to the local checkpoint, default artifacts/models/best_model.pth.",
    )
    parser.add_argument(
        "--architecture",
        default=settings.model_architecture or ARCHITECTURE_MOBILENET_V3_SMALL,
        help="Expected architecture, default mobilenet_v3_small.",
    )
    parser.add_argument(
        "--task-type",
        default=TASK_TYPE_MULTI_CLASS,
        choices=[TASK_TYPE_MULTI_CLASS],
        help="Expected task type. This Kaggle checkpoint must be multi_class.",
    )
    parser.add_argument(
        "--device",
        default=settings.model_device,
        help="Torch device, default cpu.",
    )
    return parser.parse_args()


def _checkpoint_has_state_dict(checkpoint: object) -> bool:
    if not isinstance(checkpoint, dict):
        return False
    if isinstance(checkpoint.get("model_state_dict"), dict):
        return True
    if isinstance(checkpoint.get("state_dict"), dict):
        return True
    return bool(checkpoint) and all(isinstance(key, str) for key in checkpoint)


def _validate_classifier(classifier: nn.Module) -> None:
    if not isinstance(classifier, nn.Sequential):
        raise ValueError("Expected MobileNetV3 classifier to be nn.Sequential")
    if len(classifier) != 4:
        raise ValueError("Expected MobileNetV3 classifier to contain 4 layers")
    if not isinstance(classifier[0], nn.Linear) or classifier[0].out_features != 512:
        raise ValueError("Expected classifier[0] to be Linear(..., 512)")
    if not isinstance(classifier[1], nn.Hardswish):
        raise ValueError("Expected classifier[1] to be Hardswish")
    if not isinstance(classifier[2], nn.Dropout) or classifier[2].p != 0.3:
        raise ValueError("Expected classifier[2] to be Dropout(p=0.3)")
    if (
        not isinstance(classifier[3], nn.Linear)
        or classifier[3].out_features != len(DEMO_LABELS)
    ):
        raise ValueError("Expected classifier[3] to output 4 classes")


def _build_synthetic_image() -> Image.Image:
    image = Image.new("RGB", (256, 256))
    pixels: list[tuple[int, int, int]] = []
    for y in range(256):
        for x in range(256):
            pixels.append((x, y, (x + y) // 2))
    image.putdata(pixels)
    return image


def check_model_checkpoint(
    *,
    model_path: str | Path,
    architecture: str = ARCHITECTURE_MOBILENET_V3_SMALL,
    task_type: str = TASK_TYPE_MULTI_CLASS,
    device: str = "cpu",
) -> dict[str, object]:
    if task_type != TASK_TYPE_MULTI_CLASS:
        raise ValueError("The Kaggle checkpoint task type must be multi_class")

    normalized_architecture = normalize_architecture_name(architecture)
    if normalized_architecture != ARCHITECTURE_MOBILENET_V3_SMALL:
        raise ValueError("The Kaggle checkpoint architecture must be mobilenet_v3_small")

    checkpoint_path = Path(model_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Model checkpoint not found: {checkpoint_path}")
    if not checkpoint_path.is_file():
        raise ValueError(f"Model checkpoint path is not a file: {checkpoint_path}")

    checkpoint = torch.load(checkpoint_path, map_location=device)
    if not _checkpoint_has_state_dict(checkpoint):
        raise ValueError("Checkpoint must contain model_state_dict or state_dict")

    loaded_model = load_model(
        model_source=MODEL_SOURCE_LOCAL,
        model_path=checkpoint_path,
        architecture=normalized_architecture,
        device=device,
    )
    if loaded_model.prediction_mode != PREDICTION_MODE_MULTICLASS:
        raise ValueError("MobileNetV3 checkpoint must use multiclass prediction mode")
    if set(loaded_model.label_names) != set(DEMO_LABELS):
        raise ValueError("Checkpoint labels must match the four demo labels")

    _validate_classifier(loaded_model.model.classifier)  # type: ignore[attr-defined]
    outputs = run_inference(_build_synthetic_image(), loaded_model=loaded_model)
    probabilities_sum = sum(output.probability for output in outputs)
    positive_outputs = [output for output in outputs if output.predicted_positive]
    if abs(probabilities_sum - 1.0) > 1e-5:
        raise ValueError("Multi-class probabilities must sum to 1")
    if len(positive_outputs) != 1:
        raise ValueError("Multi-class inference must produce exactly one positive label")

    return {
        "model_path": str(checkpoint_path),
        "architecture": loaded_model.architecture,
        "task_type": task_type,
        "prediction_mode": loaded_model.prediction_mode,
        "classes": list(loaded_model.label_names),
        "probabilities_sum": probabilities_sum,
        "predicted_label": positive_outputs[0].label_name,
        "checkpoint_epoch": checkpoint.get("epoch") if isinstance(checkpoint, dict) else None,
        "checkpoint_val_acc": (
            checkpoint.get("val_acc") if isinstance(checkpoint, dict) else None
        ),
    }


def main() -> None:
    args = parse_args()
    result = check_model_checkpoint(
        model_path=args.model_path,
        architecture=args.architecture,
        task_type=args.task_type,
        device=args.device,
    )

    print("Model checkpoint check passed")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
