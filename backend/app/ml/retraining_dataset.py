from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset

from app.ml.preprocessing import build_preprocessing_transform, load_image
from app.services.storage import get_image_storage

RETRAIN_CLASS_ORDER: tuple[str, ...] = (
    "Atelectasis",
    "Effusion",
    "Infiltration",
    "No_Finding",
)
DISPLAY_TO_CLASS: dict[str, str] = {
    "No Finding": "No_Finding",
    "No_Finding": "No_Finding",
}


def normalize_retraining_label(label_name: str) -> str:
    return DISPLAY_TO_CLASS.get(label_name, label_name)


def class_index_for_label(label_name: str) -> int:
    normalized = normalize_retraining_label(label_name)
    try:
        return RETRAIN_CLASS_ORDER.index(normalized)
    except ValueError as exc:
        raise ValueError(f"Unsupported retraining label: {label_name}") from exc


class RetrainingManifestDataset(Dataset[tuple[torch.Tensor, int]]):
    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.samples = list(payload.get("samples", []))
        if not self.samples:
            raise ValueError("Retraining manifest has no samples")
        self.transform = build_preprocessing_transform()
        self.storage = get_image_storage()

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        sample = self.samples[index]
        image_path = str(sample.get("image_path") or "")
        if not image_path:
            raise ValueError(f"Manifest sample {index} has no image_path")
        image_input = self.storage.get_image_input(image_path)
        image = load_image(image_input)
        label_name = self._label_name(sample)
        return self.transform(image), class_index_for_label(label_name)

    @staticmethod
    def _label_name(sample: dict[str, Any]) -> str:
        class_name = sample.get("class_name")
        if isinstance(class_name, str) and class_name:
            return class_name
        labels = sample.get("labels")
        if not isinstance(labels, dict):
            raise ValueError("Manifest sample has no labels mapping")
        positive_labels = [
            str(label_name)
            for label_name, selected in labels.items()
            if bool(selected)
        ]
        if len(positive_labels) != 1:
            raise ValueError("Each retraining sample must have exactly one label")
        return positive_labels[0]
