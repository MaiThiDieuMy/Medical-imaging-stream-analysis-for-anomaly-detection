from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset

from app.core.config import settings
from app.ml.preprocessing import build_preprocessing_transform, load_image
from app.ml.retraining_dataset import RETRAIN_CLASS_ORDER, class_index_for_label

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
FIXED_EVALUATION_SOURCE = "fixed_evaluation_set"
FALLBACK_EVALUATION_SOURCE = "training_split_or_unavailable"


@dataclass(frozen=True)
class EvaluationSetStatus:
    available: bool
    sample_count: int
    class_counts: dict[str, int]
    evaluation_source: str
    warning: str | None = None


class FixedEvaluationDataset(Dataset[tuple[torch.Tensor, int]]):
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.samples = _collect_evaluation_samples(self.root_dir)
        if not self.samples:
            raise ValueError("Fixed evaluation set has no supported images")
        self.transform = build_preprocessing_transform()

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        image_path, label_name = self.samples[index]
        image = load_image(image_path)
        return self.transform(image), class_index_for_label(label_name)


def _collect_evaluation_samples(root_dir: Path) -> list[tuple[Path, str]]:
    samples: list[tuple[Path, str]] = []
    if not root_dir.exists() or not root_dir.is_dir():
        return samples
    for label_name in RETRAIN_CLASS_ORDER:
        class_dir = root_dir / label_name
        if not class_dir.exists() or not class_dir.is_dir():
            continue
        for image_path in sorted(class_dir.iterdir()):
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_SUFFIXES:
                samples.append((image_path, label_name))
    return samples


def get_evaluation_set_status(
    evaluation_dir: str | Path | None = None,
) -> EvaluationSetStatus:
    root_dir = Path(evaluation_dir or settings.evaluation_set_dir)
    class_counts = {label_name: 0 for label_name in RETRAIN_CLASS_ORDER}
    if not root_dir.exists() or not root_dir.is_dir():
        return EvaluationSetStatus(
            available=False,
            sample_count=0,
            class_counts=class_counts,
            evaluation_source=FALLBACK_EVALUATION_SOURCE,
            warning=(
                "Fixed evaluation set is missing; retraining will fall back to "
                "validation split for pipeline testing only."
            ),
        )

    samples = _collect_evaluation_samples(root_dir)
    for _image_path, label_name in samples:
        class_counts[label_name] += 1

    if not samples:
        return EvaluationSetStatus(
            available=False,
            sample_count=0,
            class_counts=class_counts,
            evaluation_source=FALLBACK_EVALUATION_SOURCE,
            warning=(
                "Fixed evaluation set is empty; retraining will fall back to "
                "validation split for pipeline testing only."
            ),
        )

    return EvaluationSetStatus(
        available=True,
        sample_count=len(samples),
        class_counts=class_counts,
        evaluation_source=FIXED_EVALUATION_SOURCE,
        warning=None,
    )


def build_fixed_evaluation_loader(
    *,
    evaluation_dir: str | Path | None = None,
    batch_size: int | None = None,
) -> tuple[DataLoader[tuple[torch.Tensor, torch.Tensor]] | None, EvaluationSetStatus]:
    status = get_evaluation_set_status(evaluation_dir)
    if not status.available:
        return None, status
    dataset = FixedEvaluationDataset(evaluation_dir or settings.evaluation_set_dir)
    return (
        DataLoader(
            dataset,
            batch_size=batch_size or settings.retrain_batch_size,
            shuffle=False,
        ),
        status,
    )
