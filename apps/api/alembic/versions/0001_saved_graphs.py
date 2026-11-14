"""Create PostgreSQL graph snapshots."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_saved_graphs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saved_graphs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_identifier", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("seed_paper_id", sa.String(32), nullable=False),
        sa.Column("graph_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_saved_graphs_owner_identifier", "saved_graphs", ["owner_identifier"])


def downgrade():
    op.drop_index("ix_saved_graphs_owner_identifier", table_name="saved_graphs")
    op.drop_table("saved_graphs")
