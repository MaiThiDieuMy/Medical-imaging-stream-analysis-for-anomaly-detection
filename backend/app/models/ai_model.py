from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AIModel(Base):
    __tablename__ = "ai_models"
    __table_args__ = (
        UniqueConstraint("model_name", "version", name="uq_ai_models_name_version"),
        Index(
            "uq_ai_models_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    model_name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(20))
    model_path: Mapped[str] = mapped_column(Text)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    mlflow_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mlflow_model_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    mlflow_registered_model_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    mlflow_model_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        back_populates="model",
    )
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(
        back_populates="model",
    )
