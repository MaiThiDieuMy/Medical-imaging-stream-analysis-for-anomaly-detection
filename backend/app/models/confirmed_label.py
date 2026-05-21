from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ConfirmedLabel(Base):
    __tablename__ = "confirmed_labels"
    __table_args__ = (
        UniqueConstraint(
            "review_id",
            "label_name",
            name="uq_confirmed_labels_review_label",
        ),
    )

    confirmed_label_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("case_reviews.review_id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xray_cases.case_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    label_name: Mapped[str] = mapped_column(String(100), nullable=False)
    confirmed_positive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    review: Mapped["CaseReview"] = relationship(back_populates="confirmed_labels")
    case: Mapped["XRayCase"] = relationship(back_populates="confirmed_labels")
