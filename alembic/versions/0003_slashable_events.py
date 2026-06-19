# SPDX-FileCopyrightText: 2026 AI Power Grid
# SPDX-License-Identifier: AGPL-3.0-or-later
"""slashable events — append-only enforcement audit queue

Records detected worker misbehavior (forged/mismatched result receipts, repeated
health strikes). Nothing here auto-slashes; it's the evidence queue an operator
or enforcement job reviews before any deliberate on-chain WorkerRegistry.slash.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

PortableJSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "grid_slashable_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("worker_id", sa.Uuid, nullable=True),
        sa.Column("worker_name", sa.String(120), nullable=True),
        sa.Column("signer_address", sa.String(42), nullable=True),
        sa.Column("wallet", sa.String(42), nullable=True),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False, server_default="low"),
        sa.Column("detail", PortableJSON, nullable=False),
        sa.Column("reviewed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("action", sa.String(120), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_grid_slashable_events_worker_id", "grid_slashable_events", ["worker_id"])
    op.create_index("ix_grid_slashable_events_signer_address", "grid_slashable_events", ["signer_address"])
    op.create_index("ix_grid_slashable_events_wallet", "grid_slashable_events", ["wallet"])
    op.create_index("ix_grid_slashable_events_job_id", "grid_slashable_events", ["job_id"])
    op.create_index("ix_grid_slashable_events_kind", "grid_slashable_events", ["kind"])
    op.create_index("ix_grid_slashable_events_reviewed", "grid_slashable_events", ["reviewed"])
    op.create_index("ix_grid_slashable_events_created", "grid_slashable_events", ["created"])


def downgrade() -> None:
    for ix in (
        "ix_grid_slashable_events_created",
        "ix_grid_slashable_events_reviewed",
        "ix_grid_slashable_events_kind",
        "ix_grid_slashable_events_job_id",
        "ix_grid_slashable_events_wallet",
        "ix_grid_slashable_events_signer_address",
        "ix_grid_slashable_events_worker_id",
    ):
        op.drop_index(ix, table_name="grid_slashable_events")
    op.drop_table("grid_slashable_events")
