"""create core tables

Revision ID: 20260514_0001
Revises:
Create Date: 2026-05-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260514_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    user_role = postgresql.ENUM("user", "admin", name="user_role")
    processing_status = postgresql.ENUM(
        "queued",
        "processing",
        "completed",
        "failed",
        name="processing_status",
    )
    user_role.create(bind, checkfirst=True)
    processing_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("user", "admin", name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "patients",
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_code", sa.String(length=20), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("gender", sa.String(length=10), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("patient_id"),
    )
    op.create_index(
        "ix_patients_patient_code",
        "patients",
        ["patient_code"],
        unique=True,
    )

    op.create_table(
        "ai_models",
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("model_path", sa.Text(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("f1_score", sa.Float(), nullable=True),
        sa.Column("precision_score", sa.Float(), nullable=True),
        sa.Column("recall_score", sa.Float(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("model_id"),
        sa.UniqueConstraint("model_name", "version", name="uq_ai_models_name_version"),
    )
    op.create_index(
        "uq_ai_models_single_active",
        "ai_models",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "xray_cases",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued",
                "processing",
                "completed",
                "failed",
                name="processing_status",
                create_type=False,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("case_id"),
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued",
                "processing",
                "completed",
                "failed",
                name="processing_status",
                create_type=False,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["xray_cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["ai_models.model_id"]),
        sa.PrimaryKeyConstraint("job_id"),
        sa.UniqueConstraint("case_id"),
    )

    op.create_table(
        "analysis_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_name", sa.String(length=100), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("predicted_positive", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["xray_cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["ai_models.model_id"]),
        sa.PrimaryKeyConstraint("result_id"),
        sa.UniqueConstraint(
            "case_id",
            "model_id",
            "label_name",
            name="uq_analysis_results_case_model_label",
        ),
    )

    op.create_table(
        "xray_images",
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("image_path", sa.Text(), nullable=False),
        sa.Column("image_hash", sa.String(length=64), nullable=False),
        sa.Column("file_format", sa.String(length=20), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["xray_cases.case_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("image_id"),
        sa.UniqueConstraint("case_id"),
    )
    op.create_index(
        "ix_xray_images_image_hash",
        "xray_images",
        ["image_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_xray_images_image_hash", table_name="xray_images")
    op.drop_table("xray_images")
    op.drop_table("analysis_results")
    op.drop_table("analysis_jobs")
    op.drop_table("xray_cases")
    op.drop_index("uq_ai_models_single_active", table_name="ai_models")
    op.drop_table("ai_models")
    op.drop_index("ix_patients_patient_code", table_name="patients")
    op.drop_table("patients")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    postgresql.ENUM(name="processing_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="user_role").drop(bind, checkfirst=True)
