"""Phase 3 loan models

Revision ID: 0004_phase3_loan_models
Revises: 0003_phase2_ledger_models
Create Date: 2026-11-10 16:18:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_phase3_loan_models"
down_revision: str | None = "0003_phase2_ledger_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. loans table
    op.create_table(
        "loans",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("shg_id", sa.Uuid(as_uuid=True), sa.ForeignKey("shgs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("member_id", sa.Uuid(as_uuid=True), sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("loan_number", sa.String(50), nullable=False),
        sa.Column("purpose", sa.String(500), nullable=False),
        sa.Column("principal", sa.Numeric(14, 2), nullable=False),
        sa.Column("interest_rate", sa.Numeric(6, 3), nullable=False),
        sa.Column("interest_type", sa.String(50), nullable=False),
        sa.Column("tenure_months", sa.Integer(), nullable=False),
        sa.Column("processing_fee", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("status", sa.String(50), server_default="DRAFT", nullable=False),
        sa.Column("applied_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(500), nullable=True),
        sa.Column("disbursed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_due_date", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("shg_id", "loan_number", name="uq_loans_shg_id_loan_number"),
        sa.CheckConstraint("principal > 0", name="chk_loan_principal_positive"),
        sa.CheckConstraint("tenure_months >= 1", name="chk_loan_tenure_positive"),
        sa.CheckConstraint("interest_rate >= 0", name="chk_loan_interest_non_negative"),
    )
    op.create_index("ix_loans_shg_id", "loans", ["shg_id"])
    op.create_index("ix_loans_member_id", "loans", ["member_id"])
    op.create_index("ix_loans_status", "loans", ["status"])

    # 2. loan_schedule table
    op.create_table(
        "loan_schedule",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("loan_id", sa.Uuid(as_uuid=True), sa.ForeignKey("loans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("installment_no", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("principal_due", sa.Numeric(14, 2), nullable=False),
        sa.Column("interest_due", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_due", sa.Numeric(14, 2), nullable=False),
        sa.Column("principal_paid", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("interest_paid", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("penalty_paid", sa.Numeric(14, 2), server_default="0.00", nullable=False),
        sa.Column("status", sa.String(50), server_default="PENDING", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("loan_id", "installment_no", name="uq_loan_schedule_loan_inst"),
    )
    op.create_index("ix_loan_schedule_loan_id", "loan_schedule", ["loan_id"])
    op.create_index("ix_loan_schedule_status", "loan_schedule", ["status"])

    # 3. loan_status_history table
    op.create_table(
        "loan_status_history",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("loan_id", sa.Uuid(as_uuid=True), sa.ForeignKey("loans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(50), nullable=False),
        sa.Column("to_status", sa.String(50), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_loan_status_history_loan_id", "loan_status_history", ["loan_id"])


def downgrade() -> None:
    op.drop_table("loan_status_history")
    op.drop_table("loan_schedule")
    op.drop_table("loans")
