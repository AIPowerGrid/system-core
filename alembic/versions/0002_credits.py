# SPDX-FileCopyrightText: 2026 AI Power Grid
# SPDX-License-Identifier: AGPL-3.0-or-later
"""credits — prepaid balance + append-only credit ledger

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grid_credits",
        sa.Column("account_id", sa.Uuid, primary_key=True),
        sa.Column("balance_micro", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("updated", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "grid_credit_ledger",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Uuid, nullable=False),
        sa.Column("delta_micro", sa.BigInteger, nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("ref", sa.String(80), nullable=True, unique=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_grid_credit_ledger_account_id", "grid_credit_ledger", ["account_id"])
    op.create_index("ix_grid_credit_ledger_created", "grid_credit_ledger", ["created"])


def downgrade() -> None:
    op.drop_index("ix_grid_credit_ledger_created", table_name="grid_credit_ledger")
    op.drop_index("ix_grid_credit_ledger_account_id", table_name="grid_credit_ledger")
    op.drop_table("grid_credit_ledger")
    op.drop_table("grid_credits")
