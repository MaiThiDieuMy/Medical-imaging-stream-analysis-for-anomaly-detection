"""create retraining jobs table

Revision ID: 20260522_0005
Revises: 20260517_0004
Create Date: 2026-05-22 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260522_0005"
down_revision: Union[str, None] = "20260517_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retraining_jobs",
        sa.Column("retraining_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("base_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_model_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.Column("output_model_path", sa.Text(), nullable=True),
        sa.Column("mlflow_run_id", sa.String(length=100), nullable=True),
        sa.Column("mlflow_model_uri", sa.Text(), nullable=True),
        sa.Column("training_samples_count", sa.Integer(), nullable=False),
        sa.Column("min_required_samples", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("precision_score", sa.Float(), nullable=True),
        sa.Column("recall_score", sa.Float(), nullable=True),
        sa.Column("f1_score", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["base_model_id"],
            ["ai_models.model_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_model_id"],
            ["ai_models.model_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by"],
            ["users.user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("retraining_job_id"),
    )
    op.create_index(
        "ix_retraining_jobs_status",
        "retraining_jobs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_retraining_jobs_status", table_name="retraining_jobs")
    op.drop_table("retraining_jobs")
