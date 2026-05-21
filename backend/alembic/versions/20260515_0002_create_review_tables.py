"""create review and confirmed label tables

Revision ID: 20260515_0002
Revises: 20260514_0001
Create Date: 2026-05-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260515_0002"
down_revision: Union[str, None] = "20260514_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_reviews",
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["xray_cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("review_id"),
        sa.UniqueConstraint("case_id"),
    )
    op.create_index(
        "ix_case_reviews_case_id",
        "case_reviews",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        "ix_case_reviews_status",
        "case_reviews",
        ["status"],
        unique=False,
    )

    op.create_table(
        "confirmed_labels",
        sa.Column(
            "confirmed_label_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_name", sa.String(length=100), nullable=False),
        sa.Column("confirmed_positive", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["case_reviews.review_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["xray_cases.case_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("confirmed_label_id"),
        sa.UniqueConstraint(
            "review_id",
            "label_name",
            name="uq_confirmed_labels_review_label",
        ),
    )
    op.create_index(
        "ix_confirmed_labels_case_id",
        "confirmed_labels",
        ["case_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_confirmed_labels_case_id", table_name="confirmed_labels")
    op.drop_table("confirmed_labels")
    op.drop_index("ix_case_reviews_status", table_name="case_reviews")
    op.drop_index("ix_case_reviews_case_id", table_name="case_reviews")
    op.drop_table("case_reviews")
