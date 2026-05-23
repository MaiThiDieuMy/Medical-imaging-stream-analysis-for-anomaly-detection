from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DatasetManifest(Base):
    __tablename__ = "dataset_manifests"

    manifest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    manifest_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    manifest_path: Mapped[str] = mapped_column(Text, nullable=False)
    samples_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label_distribution: Mapped[dict[str, int]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    source_review_statuses: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    base_query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_by_retraining_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        "created_by",
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
