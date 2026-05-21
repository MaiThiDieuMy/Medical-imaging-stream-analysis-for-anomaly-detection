from pathlib import Path

import torch
from torch import nn
from torchvision import models

from app.core.config import settings
from app.ml.labels import DEMO_LABELS, NUM_DEMO_LABELS
from app.ml.types import (
    PREDICTION_MODE_MULTICLASS,
    PREDICTION_MODE_MULTILABEL,
    LoadedModel,
)

MODEL_SOURCE_DEMO = "demo"
MODEL_SOURCE_LOCAL = "local"
MODEL_SOURCE_MLFLOW = "mlflow"

ARCHITECTURE_DEMO = "demo"
ARCHITECTURE_DENSENET121 = "densenet121"
ARCHITECTURE_MOBILENET_V3_SMALL = "mobilenet_v3_small"
SUPPORTED_LOCAL_ARCHITECTURES = {
    ARCHITECTURE_DENSENET121,
    ARCHITECTURE_MOBILENET_V3_SMALL,
}

ARCHITECTURE_ALIASES = {
    "mobilenetv3_small": ARCHITECTURE_MOBILENET_V3_SMALL,
    "mobilenet-v3-small": ARCHITECTURE_MOBILENET_V3_SMALL,
    "mobilenet_v3_small": ARCHITECTURE_MOBILENET_V3_SMALL,
}

KAGGLE_MOBILENET_V3_SMALL_LABELS: tuple[str, ...] = (
    "Atelectasis",
    "Effusion",
    "Infiltration",
    "No Finding",
)
CHECKPOINT_LABEL_ALIASES = {
    "No_Finding": "No Finding",
    "no_finding": "No Finding",
}


class DemoChestXRayModel(nn.Module):
    """Small CPU-friendly demo model used until real weights are registered."""

    def __init__(self, num_labels: int = NUM_DEMO_LABELS) -> None:
        super().__init__()
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.classifier = nn.Linear(3, num_labels)
        self._initialize_demo_weights()

    def _initialize_demo_weights(self) -> None:
        with torch.no_grad():
            self.classifier.weight.copy_(
                torch.tensor(
                    [
                        [0.80, -0.20, -0.10],
                        [-0.30, 0.65, 0.20],
                        [0.25, 0.20, 0.55],
                        [0.10, -0.45, 0.70],
                    ],
                    dtype=self.classifier.weight.dtype,
                )
            )
            self.classifier.bias.copy_(
                torch.tensor(
                    [0.15, -0.05, 0.00, -0.10],
                    dtype=self.classifier.bias.dtype,
                )
            )

    def forward(self, image_batch: torch.Tensor) -> torch.Tensor:
        features = self.pool(image_batch).flatten(start_dim=1)
        return self.classifier(features)


def normalize_architecture_name(architecture: str) -> str:
    normalized_architecture = architecture.strip().lower()
    return ARCHITECTURE_ALIASES.get(
        normalized_architecture,
        normalized_architecture,
    )


def build_model_architecture(architecture: str) -> nn.Module:
    normalized_architecture = normalize_architecture_name(architecture)

    if normalized_architecture == ARCHITECTURE_DEMO:
        return DemoChestXRayModel(num_labels=NUM_DEMO_LABELS)

    if normalized_architecture == ARCHITECTURE_DENSENET121:
        model = models.densenet121(weights=None)
        model.classifier = nn.Linear(model.classifier.in_features, NUM_DEMO_LABELS)
        return model

    if normalized_architecture == ARCHITECTURE_MOBILENET_V3_SMALL:
        model = models.mobilenet_v3_small(weights=None)
        in_features = model.classifier[0].in_features
        model.classifier = nn.Sequential(
            nn.Linear(in_features, 512),
            nn.Hardswish(inplace=True),
            nn.Dropout(p=0.3),
            nn.Linear(512, NUM_DEMO_LABELS),
        )
        return model

    raise ValueError(
        "Unsupported model architecture "
        f"'{architecture}'. Supported local architectures: "
        f"{', '.join(sorted(SUPPORTED_LOCAL_ARCHITECTURES))}"
    )


def _extract_state_dict(checkpoint: object) -> dict[str, torch.Tensor]:
    if isinstance(checkpoint, dict):
        for key in ("state_dict", "model_state_dict"):
            value = checkpoint.get(key)
            if isinstance(value, dict):
                return value
        if all(isinstance(key, str) for key in checkpoint):
            return checkpoint  # type: ignore[return-value]

    raise ValueError(
        "Unsupported checkpoint format. Expected a state_dict or a dict containing "
        "'state_dict'/'model_state_dict'."
    )


def _strip_data_parallel_prefix(
    state_dict: dict[str, torch.Tensor],
) -> dict[str, torch.Tensor]:
    if state_dict and all(key.startswith("module.") for key in state_dict):
        return {key.removeprefix("module."): value for key, value in state_dict.items()}
    return state_dict


def _normalize_label_name(label_name: object) -> str:
    label = str(label_name)
    return CHECKPOINT_LABEL_ALIASES.get(label, label)


def _extract_label_names(
    checkpoint: object,
    *,
    architecture: str,
) -> tuple[str, ...]:
    if isinstance(checkpoint, dict):
        raw_classes = checkpoint.get("classes")
        if isinstance(raw_classes, (list, tuple)):
            label_names = tuple(_normalize_label_name(label) for label in raw_classes)
            if (
                set(label_names) != set(DEMO_LABELS)
                or len(label_names) != NUM_DEMO_LABELS
            ):
                raise ValueError(
                    "Checkpoint classes must contain exactly: "
                    + ", ".join(DEMO_LABELS)
                )
            return label_names

    if architecture == ARCHITECTURE_MOBILENET_V3_SMALL:
        return KAGGLE_MOBILENET_V3_SMALL_LABELS

    return DEMO_LABELS


def _prediction_mode_for_architecture(architecture: str) -> str:
    if architecture == ARCHITECTURE_MOBILENET_V3_SMALL:
        return PREDICTION_MODE_MULTICLASS
    return PREDICTION_MODE_MULTILABEL


def _load_local_model(
    *,
    model_path: str | Path,
    architecture: str,
    device: torch.device,
) -> LoadedModel:
    normalized_architecture = normalize_architecture_name(architecture)
    checkpoint_path = Path(model_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Model weights not found: {checkpoint_path}")
    if not checkpoint_path.is_file():
        raise ValueError(f"Model weights path is not a file: {checkpoint_path}")

    model = build_model_architecture(normalized_architecture)
    checkpoint = torch.load(checkpoint_path, map_location=device)
    state_dict = _strip_data_parallel_prefix(_extract_state_dict(checkpoint))
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()

    return LoadedModel(
        model=model,
        device=device,
        label_names=_extract_label_names(
            checkpoint,
            architecture=normalized_architecture,
        ),
        source=MODEL_SOURCE_LOCAL,
        architecture=normalized_architecture,
        weights_path=checkpoint_path,
        prediction_mode=_prediction_mode_for_architecture(normalized_architecture),
    )


def load_model(
    model_source: str | None = None,
    model_path: str | Path | None = None,
    architecture: str | None = None,
    device: str | torch.device | None = None,
    allow_demo_model: bool | None = None,
) -> LoadedModel:
    source = (model_source or settings.model_source).strip().lower()
    target_device = torch.device(device or settings.model_device)
    configured_path = model_path or settings.model_weights_path or None
    configured_architecture = normalize_architecture_name(
        architecture or settings.model_architecture
    )
    demo_allowed = (
        settings.allow_demo_model if allow_demo_model is None else allow_demo_model
    )

    if source == MODEL_SOURCE_DEMO:
        if not demo_allowed:
            raise RuntimeError("Demo model is disabled by configuration")

        model = DemoChestXRayModel(num_labels=NUM_DEMO_LABELS)
        model.to(target_device)
        model.eval()

        return LoadedModel(
            model=model,
            device=target_device,
            label_names=DEMO_LABELS,
            source=MODEL_SOURCE_DEMO,
            architecture=ARCHITECTURE_DEMO,
            weights_path=None,
            prediction_mode=PREDICTION_MODE_MULTILABEL,
        )

    if source == MODEL_SOURCE_LOCAL:
        if configured_path is None:
            raise ValueError(
                "MODEL_SOURCE=local requires MODEL_WEIGHTS_PATH or model_path"
            )
        return _load_local_model(
            model_path=configured_path,
            architecture=configured_architecture,
            device=target_device,
        )

    if source == MODEL_SOURCE_MLFLOW:
        raise NotImplementedError(
            "MODEL_SOURCE=mlflow is reserved for Phase 5 MLflow registry integration"
        )

    raise ValueError(
        f"Unsupported MODEL_SOURCE '{source}'. Use demo, local, or mlflow."
    )
