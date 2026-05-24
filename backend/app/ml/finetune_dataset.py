from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import torch
from torch.utils.data import Dataset

from app.core.config import settings
from app.ml.evaluation_set import IMAGE_SUFFIXES
from app.ml.preprocessing import build_preprocessing_transform, load_image
from app.ml.retraining_dataset import (
    RETRAIN_CLASS_ORDER,
    class_index_for_label,
    normalize_retraining_label,
)
from app.services.storage import get_image_storage

SOURCE_SEED = "seed"
SOURCE_CONFIRMED_CASE = "confirmed_case"


class ConfirmedCaseSampleLike(Protocol):
    review_id: Any
    case_id: Any
    image_path: str
    image_hash: str | None
    label_name: str
    label_index: int
    review_status: str
    reviewed_by: Any | None
    created_at: datetime
    confirmed_labels: list[dict[str, object]]


@dataclass(frozen=True)
class FineTuneSample:
    source: str
    image_path: str
    label_name: str
    label_index: int
    class_name: str
    image_hash: str | None = None
    review_id: str | None = None
    case_id: str | None = None
    review_status: str | None = None
    reviewed_by: str | None = None
    created_at: str | None = None
    labels: dict[str, bool] | None = None

    def dedupe_key(self) -> str:
        if self.image_hash:
            return f"hash:{self.image_hash}"
        return f"path:{_normalized_path_key(self.image_path)}"

    def to_manifest(self) -> dict[str, object]:
        sample: dict[str, object] = {
            "source": self.source,
            "image_path": self.image_path,
            "label_name": self.label_name,
            "label_index": self.label_index,
            "class_name": self.class_name,
            "image_hash": self.image_hash,
        }
        if self.source == SOURCE_SEED:
            sample["path"] = self.image_path
        else:
            sample.update(
                {
                    "object_key": self.image_path,
                    "review_id": self.review_id,
                    "case_id": self.case_id,
                    "review_status": self.review_status,
                    "reviewed_by": self.reviewed_by,
                    "created_at": self.created_at,
                    "labels": self.labels or {},
                }
            )
        return sample


@dataclass(frozen=True)
class FineTuneDatasetSummary:
    samples: list[FineTuneSample]
    seed_count: int
    confirmed_count: int
    total_train_count: int
    per_class_count: dict[str, int]


class FineTuneManifestDataset(Dataset[tuple[torch.Tensor, int]]):
    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.samples = list(payload.get("samples", []))
        if not self.samples:
            raise ValueError("Fine-tune manifest has no samples")
        self.transform = build_preprocessing_transform()
        self.storage = get_image_storage()

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        sample = self.samples[index]
        image_path = str(sample.get("image_path") or sample.get("path") or "")
        if not image_path:
            raise ValueError(f"Manifest sample {index} has no image_path")
        if sample.get("source") == SOURCE_SEED:
            image = load_image(Path(image_path))
        else:
            image = load_image(self.storage.get_image_input(image_path))
        return self.transform(image), int(sample["label_index"])


def load_training_seed_samples(
    training_seed_dir: str | Path | None = None,
    *,
    max_per_class: int | None = None,
) -> list[FineTuneSample]:
    root_dir = Path(training_seed_dir or settings.training_seed_dir)
    if max_per_class is None:
        max_per_class = settings.retrain_seed_max_per_class
    if max_per_class <= 0 or not root_dir.exists() or not root_dir.is_dir():
        return []

    samples: list[FineTuneSample] = []
    for class_name in RETRAIN_CLASS_ORDER:
        collected = 0
        seen_paths: set[str] = set()
        for class_dir in _class_dirs(root_dir, class_name):
            if collected >= max_per_class:
                break
            if not class_dir.exists() or not class_dir.is_dir():
                continue
            for image_path in sorted(class_dir.iterdir()):
                if collected >= max_per_class:
                    break
                if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                normalized_path = _normalized_path_key(str(image_path))
                if normalized_path in seen_paths:
                    continue
                seen_paths.add(normalized_path)
                samples.append(
                    FineTuneSample(
                        source=SOURCE_SEED,
                        image_path=str(image_path),
                        label_name=_display_label(class_name),
                        label_index=class_index_for_label(class_name),
                        class_name=class_name,
                    )
                )
                collected += 1
    return samples


def load_confirmed_case_samples(
    sample_items: Iterable[ConfirmedCaseSampleLike],
) -> list[FineTuneSample]:
    samples: list[FineTuneSample] = []
    for item in sample_items:
        if not item.image_path or _local_image_missing(item.image_path):
            continue
        class_name = normalize_retraining_label(item.label_name)
        labels = {
            str(label["label_name"]): bool(label["confirmed_positive"])
            for label in item.confirmed_labels
        }
        samples.append(
            FineTuneSample(
                source=SOURCE_CONFIRMED_CASE,
                image_path=item.image_path,
                image_hash=item.image_hash,
                label_name=_display_label(class_name),
                label_index=item.label_index,
                class_name=class_name,
                review_id=str(item.review_id),
                case_id=str(item.case_id),
                review_status=item.review_status,
                reviewed_by=str(item.reviewed_by) if item.reviewed_by else None,
                created_at=item.created_at.isoformat(),
                labels=labels,
            )
        )
    return samples


def build_finetune_dataset(
    confirmed_sample_items: Iterable[ConfirmedCaseSampleLike],
    *,
    include_training_seed: bool | None = None,
    training_seed_dir: str | Path | None = None,
    seed_max_per_class: int | None = None,
) -> FineTuneDatasetSummary:
    include_seed = (
        settings.retrain_include_training_seed
        if include_training_seed is None
        else include_training_seed
    )
    seed_samples = (
        load_training_seed_samples(
            training_seed_dir,
            max_per_class=seed_max_per_class,
        )
        if include_seed
        else []
    )
    confirmed_samples = load_confirmed_case_samples(confirmed_sample_items)
    samples = _dedupe_samples(seed_samples, confirmed_samples)
    source_counts = Counter(sample.source for sample in samples)
    per_class_counts = {class_name: 0 for class_name in RETRAIN_CLASS_ORDER}
    for sample in samples:
        per_class_counts[sample.class_name] += 1
    return FineTuneDatasetSummary(
        samples=samples,
        seed_count=source_counts[SOURCE_SEED],
        confirmed_count=source_counts[SOURCE_CONFIRMED_CASE],
        total_train_count=len(samples),
        per_class_count=per_class_counts,
    )


def _dedupe_samples(
    seed_samples: list[FineTuneSample],
    confirmed_samples: list[FineTuneSample],
) -> list[FineTuneSample]:
    by_key: dict[str, FineTuneSample] = {}
    for sample in seed_samples:
        by_key[sample.dedupe_key()] = sample
    for sample in confirmed_samples:
        by_key[sample.dedupe_key()] = sample
    return list(by_key.values())


def _class_dirs(root_dir: Path, class_name: str) -> list[Path]:
    names = [class_name]
    if class_name == "No_Finding":
        names.append("No Finding")
    return [root_dir / name for name in names]


def _display_label(class_name: str) -> str:
    return "No Finding" if class_name == "No_Finding" else class_name


def _normalized_path_key(image_path: str) -> str:
    return Path(image_path).as_posix().lower()


def _local_image_missing(image_path: str) -> bool:
    parsed = urlparse(image_path)
    if parsed.scheme in {"minio", "s3", "demo"}:
        return False
    path = Path(parsed.path) if parsed.scheme == "file" else Path(image_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return not path.is_file()
