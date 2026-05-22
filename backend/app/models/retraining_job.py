from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RetrainingJob(Base):
    __tablename__ = "retraining_jobs"

    retraining_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    base_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_models.model_id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_models.model_id", ondelete="SET NULL"),
        nullable=True,
    )
    manifest_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_model_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mlflow_model_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_samples_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_required_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        "triggered_by",
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    base_model: Mapped["AIModel"] = relationship(foreign_keys=[base_model_id])
    candidate_model: Mapped["AIModel | None"] = relationship(
        foreign_keys=[candidate_model_id],
    )
    triggered_by: Mapped["User | None"] = relationship(foreign_keys=[triggered_by_id])
