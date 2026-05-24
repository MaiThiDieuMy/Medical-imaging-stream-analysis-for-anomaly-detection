"""add trigger type to retraining jobs

Revision ID: 20260523_0006
Revises: 20260522_0005
Create Date: 2026-05-23 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0006"
down_revision: Union[str, None] = "20260522_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "retraining_jobs",
        sa.Column(
            "trigger_type",
            sa.String(length=20),
            nullable=False,
            server_default="manual",
        ),
    )


def downgrade() -> None:
    op.drop_column("retraining_jobs", "trigger_type")
