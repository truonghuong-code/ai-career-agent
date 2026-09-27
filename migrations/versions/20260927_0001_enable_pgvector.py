"""Enable pgvector extension.

Revision ID: 20260927_0001
Revises:
Create Date: 2026-09-27
"""

from alembic import op

revision = "20260927_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
