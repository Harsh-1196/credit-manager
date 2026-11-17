"""Phase 5 outbox events, consumer logs and dashboard read model

Revision ID: 0006_phase5_outbox_readmodel
Revises: 0005_phase3b_loan_disbursal_repayment
Create Date: 2026-11-17 13:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_phase5_outbox_readmodel"
down_revision: str | None = "0005_phase3b_loan_disbursal_repayment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create outbox_events table
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("shg_id", sa.Uuid(as_uuid=True), sa.ForeignKey("shgs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB, "postgresql"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_aggregate_type", "outbox_events", ["aggregate_type"])
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_shg_id", "outbox_events", ["shg_id"])
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    op.create_index("ix_outbox_events_next_retry_at", "outbox_events", ["next_retry_at"])

    # 2. Create outbox_consumer_logs table
    op.create_table(
        "outbox_consumer_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("consumer_name", sa.String(100), nullable=False),
        sa.Column("event_id", sa.Uuid(as_uuid=True), sa.ForeignKey("outbox_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shg_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("consumer_name", "event_id", name="uq_outbox_consumer_log_consumer_event"),
    )
    op.create_index("ix_outbox_consumer_logs_consumer_name", "outbox_consumer_logs", ["consumer_name"])
    op.create_index("ix_outbox_consumer_logs_event_id", "outbox_consumer_logs", ["event_id"])
    op.create_index("ix_outbox_consumer_logs_shg_id", "outbox_consumer_logs", ["shg_id"])

    # 3. Create dashboard_read_models table
    op.create_table(
        "dashboard_read_models",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shg_id", sa.Uuid(as_uuid=True), sa.ForeignKey("shgs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("total_savings", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("total_loans_disbursed", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("total_principal_outstanding", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("total_interest_collected", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("total_penalties_collected", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("group_cash_balance", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("active_loans_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overdue_loans_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("par_30_amount", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("par_60_amount", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("par_90_amount", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("last_event_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("last_event_type", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dashboard_read_models_shg_id", "dashboard_read_models", ["shg_id"])

    # 4. Create reconciliation_runs table
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("triggered_by", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="COMPLETED"),
        sa.Column("groups_checked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discrepancies_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discrepancies", sa.JSON().with_variant(postgresql.JSONB, "postgresql"), nullable=False),
    )
    op.create_index("ix_reconciliation_runs_run_at", "reconciliation_runs", ["run_at"])
    op.create_index("ix_reconciliation_runs_status", "reconciliation_runs", ["status"])


def downgrade() -> None:
    op.drop_table("reconciliation_runs")
    op.drop_table("dashboard_read_models")
    op.drop_table("outbox_consumer_logs")
    op.drop_table("outbox_events")
