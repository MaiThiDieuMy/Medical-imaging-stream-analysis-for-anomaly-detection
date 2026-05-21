from pathlib import Path
import sys

from PIL import Image
import pytest
import torch
from torch import nn

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ml.inference import run_inference  # noqa: E402
from app.ml.labels import DEMO_LABELS  # noqa: E402
from app.ml.model_loader import (  # noqa: E402
    ARCHITECTURE_MOBILENET_V3_SMALL,
    MODEL_SOURCE_LOCAL,
    build_model_architecture,
    load_model,
)
from app.ml.preprocessing import DEFAULT_IMAGE_SIZE, preprocess_image  # noqa: E402
from app.ml.types import (  # noqa: E402
    PREDICTION_MODE_MULTICLASS,
    LoadedModel,
)


def create_synthetic_image() -> Image.Image:
    image = Image.new("RGB", (256, 256))
    pixels: list[tuple[int, int, int]] = []
    for y in range(256):
        for x in range(256):
            pixels.append((x, y, (x + y) // 2))
    image.putdata(pixels)
    return image


def test_preprocess_image_returns_expected_tensor_shape() -> None:
    tensor = preprocess_image(create_synthetic_image())

    assert tensor.shape == (1, 3, DEFAULT_IMAGE_SIZE, DEFAULT_IMAGE_SIZE)
    assert tensor.device.type == "cpu"
    assert torch.isfinite(tensor).all()


def test_demo_inference_returns_four_valid_label_outputs() -> None:
    outputs = run_inference(create_synthetic_image(), threshold=0.5)

    assert len(outputs) == 4
    assert tuple(output.label_name for output in outputs) == DEMO_LABELS
    assert DEMO_LABELS == (
        "No Finding",
        "Effusion",
        "Infiltration",
        "Atelectasis",
    )

    for output in outputs:
        assert isinstance(output.probability, float)
        assert 0.0 <= output.probability <= 1.0
        assert isinstance(output.predicted_positive, bool)


def test_mobilenetv3_small_architecture_matches_kaggle_classifier() -> None:
    model = build_model_architecture(ARCHITECTURE_MOBILENET_V3_SMALL)

    assert isinstance(model.classifier, nn.Sequential)
    assert isinstance(model.classifier[0], nn.Linear)
    assert model.classifier[0].out_features == 512
    assert isinstance(model.classifier[1], nn.Hardswish)
    assert isinstance(model.classifier[2], nn.Dropout)
    assert model.classifier[2].p == 0.3
    assert isinstance(model.classifier[3], nn.Linear)
    assert model.classifier[3].out_features == len(DEMO_LABELS)


class FixedMulticlassModel(nn.Module):
    def forward(self, image_batch: torch.Tensor) -> torch.Tensor:
        batch_size = image_batch.shape[0]
        logits = torch.tensor([[0.1, 2.0, -1.0, 0.4]], dtype=image_batch.dtype)
        return logits.repeat(batch_size, 1)


def test_multiclass_inference_uses_softmax_and_single_positive_label() -> None:
    loaded_model = LoadedModel(
        model=FixedMulticlassModel(),
        device=torch.device("cpu"),
        label_names=DEMO_LABELS,
        source=MODEL_SOURCE_LOCAL,
        architecture=ARCHITECTURE_MOBILENET_V3_SMALL,
        prediction_mode=PREDICTION_MODE_MULTICLASS,
    )

    outputs = run_inference(
        create_synthetic_image(),
        loaded_model=loaded_model,
        threshold=0.99,
    )

    assert len(outputs) == len(DEMO_LABELS)
    assert abs(sum(output.probability for output in outputs) - 1.0) < 1e-6
    assert [output.predicted_positive for output in outputs].count(True) == 1
    assert outputs[1].label_name == "Effusion"
    assert outputs[1].predicted_positive is True


def test_real_kaggle_mobilenetv3_checkpoint_loads_when_available() -> None:
    checkpoint_path = BACKEND_ROOT.parent / "artifacts" / "models" / "best_model.pth"
    if not checkpoint_path.exists():
        pytest.skip("Local Kaggle MobileNetV3-Small checkpoint is not present")

    loaded_model = load_model(
        model_source=MODEL_SOURCE_LOCAL,
        model_path=checkpoint_path,
        architecture=ARCHITECTURE_MOBILENET_V3_SMALL,
        device="cpu",
    )
    outputs = run_inference(create_synthetic_image(), loaded_model=loaded_model)

    assert loaded_model.prediction_mode == PREDICTION_MODE_MULTICLASS
    assert tuple(output.label_name for output in outputs) == (
        "Atelectasis",
        "Effusion",
        "Infiltration",
        "No Finding",
    )
    assert abs(sum(output.probability for output in outputs) - 1.0) < 1e-5
    assert [output.predicted_positive for output in outputs].count(True) == 1
