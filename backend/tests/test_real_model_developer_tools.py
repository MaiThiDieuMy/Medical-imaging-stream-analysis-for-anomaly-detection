from pathlib import Path
import sys

import pytest
import torch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ml.model_loader import (  # noqa: E402
    ARCHITECTURE_MOBILENET_V3_SMALL,
    build_model_architecture,
)
from app.ml.types import (  # noqa: E402
    PREDICTION_MODE_MULTICLASS,
    PREDICTION_MODE_MULTILABEL,
)
from scripts.check_model_checkpoint import (  # noqa: E402
    TASK_TYPE_MULTI_CLASS,
    check_model_checkpoint,
)
from scripts.run_local_inference import (  # noqa: E402
    TASK_TYPE_MULTI_CLASS as CLI_TASK_TYPE_MULTI_CLASS,
    TASK_TYPE_MULTI_LABEL,
    ensure_task_type_matches_model,
    normalize_task_type,
)


def _write_mobilenet_checkpoint(path: Path) -> None:
    model = build_model_architecture(ARCHITECTURE_MOBILENET_V3_SMALL)
    torch.save(
        {
            "epoch": 3,
            "model_state_dict": model.state_dict(),
            "val_acc": 0.5,
            "classes": ["Atelectasis", "Effusion", "Infiltration", "No_Finding"],
        },
        path,
    )


def test_check_model_checkpoint_validates_mobilenetv3_multiclass(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "best_model.pth"
    _write_mobilenet_checkpoint(checkpoint_path)

    result = check_model_checkpoint(
        model_path=checkpoint_path,
        architecture=ARCHITECTURE_MOBILENET_V3_SMALL,
        task_type=TASK_TYPE_MULTI_CLASS,
        device="cpu",
    )

    assert result["architecture"] == ARCHITECTURE_MOBILENET_V3_SMALL
    assert result["task_type"] == TASK_TYPE_MULTI_CLASS
    assert result["prediction_mode"] == PREDICTION_MODE_MULTICLASS
    assert result["classes"] == [
        "Atelectasis",
        "Effusion",
        "Infiltration",
        "No Finding",
    ]
    assert abs(float(result["probabilities_sum"]) - 1.0) < 1e-5
    assert result["predicted_label"] in result["classes"]


def test_run_local_inference_task_type_aliases_and_guards() -> None:
    assert normalize_task_type("multi_class") == CLI_TASK_TYPE_MULTI_CLASS
    assert normalize_task_type("multiclass") == CLI_TASK_TYPE_MULTI_CLASS
    assert normalize_task_type("single-label") == CLI_TASK_TYPE_MULTI_CLASS
    assert normalize_task_type("multi_label") == TASK_TYPE_MULTI_LABEL

    ensure_task_type_matches_model("multi_class", PREDICTION_MODE_MULTICLASS)
    with pytest.raises(ValueError, match="expects prediction mode"):
        ensure_task_type_matches_model("multi_class", PREDICTION_MODE_MULTILABEL)
    with pytest.raises(ValueError, match="Unsupported task type"):
        normalize_task_type("segmentation")
