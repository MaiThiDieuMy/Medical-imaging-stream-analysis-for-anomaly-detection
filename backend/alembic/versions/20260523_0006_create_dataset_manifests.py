"""create dataset manifests registry

Revision ID: 20260523_0006
Revises: 20260522_0005
Create Date: 2026-05-23 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260523_0006"
down_revision: Union[str, None] = "20260522_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_manifests",
        sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("manifest_path", sa.Text(), nullable=False),
        sa.Column("samples_count", sa.Integer(), nullable=False),
        sa.Column("label_distribution", sa.JSON(), nullable=False),
        sa.Column("source_review_statuses", sa.JSON(), nullable=False),
        sa.Column("base_query_hash", sa.String(length=64), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False),
        sa.Column(
            "used_by_retraining_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("manifest_id"),
        sa.UniqueConstraint("version"),
    )
    op.create_index(
        "ix_dataset_manifests_manifest_name",
        "dataset_manifests",
        ["manifest_name"],
        unique=False,
    )
    op.add_column(
        "retraining_jobs",
        sa.Column("dataset_manifest_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_retraining_jobs_dataset_manifest_id",
        "retraining_jobs",
        "dataset_manifests",
        ["dataset_manifest_id"],
        ["manifest_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_retraining_jobs_dataset_manifest_id",
        "retraining_jobs",
        type_="foreignkey",
    )
    op.drop_column("retraining_jobs", "dataset_manifest_id")
    op.drop_index(
        "ix_dataset_manifests_manifest_name",
        table_name="dataset_manifests",
    )
    op.drop_table("dataset_manifests")
