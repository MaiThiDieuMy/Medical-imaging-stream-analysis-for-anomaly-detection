from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dataset_manifest import DatasetManifest


def create_dataset_manifest(
    db: Session,
    *,
    manifest_name: str,
    version: str,
    manifest_path: str,
    samples_count: int,
    label_distribution: dict[str, int],
    source_review_statuses: list[str],
    base_query_hash: str,
    created_by: uuid.UUID | None,
    metadata_json: dict[str, object] | None = None,
) -> DatasetManifest:
    manifest = DatasetManifest(
        manifest_name=manifest_name,
        version=version,
        manifest_path=manifest_path,
        samples_count=samples_count,
        label_distribution=label_distribution,
        source_review_statuses=source_review_statuses,
        base_query_hash=base_query_hash,
        created_by_id=created_by,
        metadata_json=metadata_json,
        is_locked=False,
    )
    db.add(manifest)
    db.flush()
    return manifest


def get_dataset_manifest(
    db: Session,
    *,
    manifest_id: uuid.UUID,
) -> DatasetManifest | None:
    return db.execute(
        select(DatasetManifest).where(DatasetManifest.manifest_id == manifest_id)
    ).scalar_one_or_none()


def list_dataset_manifests(db: Session) -> list[DatasetManifest]:
    return list(
        db.execute(
            select(DatasetManifest).order_by(DatasetManifest.created_at.desc())
        ).scalars()
    )


def get_latest_dataset_manifest(db: Session) -> DatasetManifest | None:
    return db.execute(
        select(DatasetManifest).order_by(DatasetManifest.created_at.desc())
    ).scalars().first()
