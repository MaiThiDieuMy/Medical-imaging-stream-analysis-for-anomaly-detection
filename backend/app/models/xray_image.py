from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class XRayImage(Base):
    __tablename__ = "xray_images"
    __table_args__ = (
        Index("ix_xray_images_image_hash", "image_hash"),
    )

    image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xray_cases.case_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255))
    image_path: Mapped[str] = mapped_column(Text)
    image_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_format: Mapped[str] = mapped_column(String(20))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    case: Mapped["XRayCase"] = relationship(back_populates="image")
