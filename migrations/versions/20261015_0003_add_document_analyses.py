"""Add versioned CV/JD analyses with source snapshots.

Revision ID: 20261015_0003
Revises: 20260927_0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261015_0003"
down_revision = "20260927_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_analyses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(2), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("document_checksum", sa.String(64), nullable=False),
        sa.Column("profile", JSONB(), nullable=False),
        sa.Column("sources", JSONB(), nullable=False),
        sa.Column("provenance", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "document_id", "kind", "version", name="uq_analysis_document_kind_version"
        ),
        sa.CheckConstraint("version > 0", name="ck_analysis_positive_version"),
        sa.CheckConstraint("kind IN ('cv', 'jd')", name="ck_analysis_kind"),
        sa.CheckConstraint(
            "status IN ('completed', 'insufficient_evidence')", name="ck_analysis_status"
        ),
    )
    op.create_index("ix_document_analyses_document_id", "document_analyses", ["document_id"])
    op.create_index("ix_document_analyses_owner_id", "document_analyses", ["owner_id"])


def downgrade() -> None:
    op.drop_table("document_analyses")
