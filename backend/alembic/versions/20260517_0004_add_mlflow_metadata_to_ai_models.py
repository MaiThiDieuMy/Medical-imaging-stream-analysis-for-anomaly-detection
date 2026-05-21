"""add mlflow metadata to ai_models

Revision ID: 20260517_0004
Revises: 20260517_0003
Create Date: 2026-05-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260517_0004"
down_revision: Union[str, None] = "20260517_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_models",
        sa.Column("mlflow_run_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "ai_models",
        sa.Column("mlflow_model_uri", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_models",
        sa.Column(
            "mlflow_registered_model_name",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "ai_models",
        sa.Column("mlflow_model_version", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_models", "mlflow_model_version")
    op.drop_column("ai_models", "mlflow_registered_model_name")
    op.drop_column("ai_models", "mlflow_model_uri")
    op.drop_column("ai_models", "mlflow_run_id")
