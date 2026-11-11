"""Phase 3b loan disbursal, repayment, penalty and write-off models

Revision ID: 0005_phase3b_loan_disbursal_repayment
Revises: 0004_phase3_loan_models
Create Date: 2026-11-11 12:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_phase3b_loan_disbursal_repayment"
down_revision: str | None = "0004_phase3_loan_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add columns to loans
    with op.batch_alter_table("loans") as batch_op:
        batch_op.add_column(
            sa.Column(
                "disbursed_by",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "written_off_by",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("written_off_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("write_off_reason", sa.Text(), nullable=True))

    # 2. Add columns to loan_schedule
    with op.batch_alter_table("loan_schedule") as batch_op:
        batch_op.add_column(
            sa.Column(
                "penalty_due",
                sa.Numeric(14, 2),
                server_default="0.00",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("last_penalty_accrual_date", sa.Date(), nullable=True))

    # 3. Add column to group_settings
    with op.batch_alter_table("group_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "prepayment_policy",
                sa.String(50),
                server_default="REDUCE_TENURE",
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("group_settings") as batch_op:
        batch_op.drop_column("prepayment_policy")

    with op.batch_alter_table("loan_schedule") as batch_op:
        batch_op.drop_column("last_penalty_accrual_date")
        batch_op.drop_column("penalty_due")

    with op.batch_alter_table("loans") as batch_op:
        batch_op.drop_column("write_off_reason")
        batch_op.drop_column("written_off_at")
        batch_op.drop_column("written_off_by")
        batch_op.drop_column("disbursed_by")
