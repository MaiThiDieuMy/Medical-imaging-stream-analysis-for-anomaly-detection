from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TypeAlias

from PIL import Image
import torch
from torch import nn

ImageInput: TypeAlias = str | Path | bytes | BinaryIO | Image.Image
PREDICTION_MODE_MULTILABEL = "multilabel"
PREDICTION_MODE_MULTICLASS = "multiclass"


@dataclass(frozen=True)
class LoadedModel:
    model: nn.Module
    device: torch.device
    label_names: tuple[str, ...]
    source: str
    architecture: str
    weights_path: Path | None = None
    prediction_mode: str = PREDICTION_MODE_MULTILABEL


@dataclass(frozen=True)
class InferenceOutput:
    label_name: str
    probability: float
    predicted_positive: bool

    def to_dict(self) -> dict[str, str | float | bool]:
        return {
            "label_name": self.label_name,
            "probability": self.probability,
            "predicted_positive": self.predicted_positive,
        }
