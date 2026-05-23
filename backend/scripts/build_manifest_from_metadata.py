from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

CLASS_ORDER = ("Atelectasis", "Effusion", "Infiltration", "No_Finding")
DISPLAY_TO_CLASS = {
    "No Finding": "No_Finding",
    "No_Finding": "No_Finding",
}


def _normalize_label(label_name: str) -> str:
    return DISPLAY_TO_CLASS.get(label_name, label_name)


def _labels_for(class_name: str) -> dict[str, bool]:
    return {
        "Atelectasis": class_name == "Atelectasis",
        "Effusion": class_name == "Effusion",
        "Infiltration": class_name == "Infiltration",
        "No Finding": class_name == "No_Finding",
    }


def build_manifest(
    *,
    metadata_path: Path,
    output_path: Path,
    manifest_name: str,
    source: str,
    limit_per_class: int,
) -> None:
    counts: Counter[str] = Counter()
    samples: list[dict[str, object]] = []
    with metadata_path.open(newline="", encoding="utf-8") as metadata_file:
        reader = csv.DictReader(metadata_file)
        for row in reader:
            image_path = (row.get("image_path") or "").strip()
            raw_label = (row.get("label") or "").strip()
            if not image_path or not raw_label:
                continue

            class_name = _normalize_label(raw_label)
            if class_name not in CLASS_ORDER:
                continue
            if limit_per_class > 0 and counts[class_name] >= limit_per_class:
                continue

            row_source = (row.get("source") or source).strip()
            samples.append(
                {
                    "review_id": None,
                    "case_id": None,
                    "image_id": None,
                    "review_status": source,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "image_path": image_path,
                    "image_hash": hashlib.sha256(image_path.encode("utf-8")).hexdigest(),
                    "analysis_job_id": None,
                    "source_model_id": None,
                    "source_model_version": None,
                    "ai_predictions": [],
                    "doctor_labels": _labels_for(class_name),
                    "labels": _labels_for(class_name),
                    "class_name": class_name,
                    "source": row_source,
                }
            )
            counts[class_name] += 1

    if not samples:
        raise SystemExit(f"No usable samples found in {metadata_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "manifest_id": None,
        "manifest_name": manifest_name,
        "version": f"{manifest_name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "created_at": created_at,
        "created_by": None,
        "samples_count": len(samples),
        "label_distribution": dict(counts),
        "source_review_statuses": [source],
        "base_query_hash": hashlib.sha256(
            json.dumps(
                [sample["image_path"] for sample in samples],
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "selection_strategy": source,
        "task_type": "multi_class_single_label",
        "class_order": list(CLASS_ORDER),
        "display_labels": {"No_Finding": "No Finding"},
        "samples": samples,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a retraining/evaluation JSON manifest from metadata CSV.",
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest-name", default="kaggle-eval-holdout")
    parser.add_argument("--source", default="fixed_eval_holdout")
    parser.add_argument("--limit-per-class", type=int, default=0)
    args = parser.parse_args()

    build_manifest(
        metadata_path=args.metadata,
        output_path=args.output,
        manifest_name=args.manifest_name,
        source=args.source,
        limit_per_class=args.limit_per_class,
    )


if __name__ == "__main__":
    main()
