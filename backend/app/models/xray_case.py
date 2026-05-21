from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ProcessingStatus, enum_values


class XRayCase(Base):
    __tablename__ = "xray_cases"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.patient_id"),
        nullable=False,
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        "uploaded_by",
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(
            ProcessingStatus,
            name="processing_status",
            values_callable=enum_values,
        ),
        default=ProcessingStatus.QUEUED,
        server_default=ProcessingStatus.QUEUED.value,
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    patient: Mapped["Patient"] = relationship(back_populates="xray_cases")
    uploaded_by: Mapped["User | None"] = relationship(back_populates="xray_cases")
    image: Mapped["XRayImage | None"] = relationship(
        back_populates="case",
        uselist=False,
        cascade="all, delete-orphan",
    )
    analysis_job: Mapped["AnalysisJob | None"] = relationship(
        back_populates="case",
        uselist=False,
        cascade="all, delete-orphan",
    )
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    review: Mapped["CaseReview | None"] = relationship(
        back_populates="case",
        uselist=False,
        cascade="all, delete-orphan",
    )
    confirmed_labels: Mapped[list["ConfirmedLabel"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
