"""Phase 2 models: accounts, journal_entries, journal_lines, meetings, attendance, savings_dues, idempotency_keys

Revision ID: 0003_phase2_ledger_models
Revises: 0002_phase1_models
Create Date: 2026-11-10 15:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_phase2_ledger_models"
down_revision: str | None = "0002_phase1_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1. accounts
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shg_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shg_id"], ["shgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shg_id", "code", name="uq_accounts_shg_id_code"),
    )
    op.create_index("ix_accounts_shg_id", "accounts", ["shg_id"])
    op.create_index("ix_accounts_code", "accounts", ["code"])
    op.create_index("ix_accounts_type", "accounts", ["type"])
    op.create_index("ix_accounts_member_id", "accounts", ["member_id"])

    # 2. journal_entries
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shg_id", sa.Uuid(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("reverses_entry_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("posted_by", sa.Uuid(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shg_id"], ["shgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reverses_entry_id"], ["journal_entries.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reverses_entry_id", name="uq_journal_entries_reverses_entry_id"),
        sa.UniqueConstraint("shg_id", "idempotency_key", name="uq_journal_entries_shg_idempotency_key"),
    )
    op.create_index("ix_journal_entries_shg_id", "journal_entries", ["shg_id"])
    op.create_index("ix_journal_entries_entry_date", "journal_entries", ["entry_date"])
    op.create_index("ix_journal_entries_source_type", "journal_entries", ["source_type"])
    op.create_index("ix_journal_entries_source_id", "journal_entries", ["source_id"])
    op.create_index("ix_journal_entries_idempotency_key", "journal_entries", ["idempotency_key"])

    # 3. journal_lines
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("debit", sa.Numeric(precision=14, scale=2), server_default="0.00", nullable=False),
        sa.Column("credit", sa.Numeric(precision=14, scale=2), server_default="0.00", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["journal_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "((debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0))",
            name="chk_journal_line_debit_xor_credit",
        ),
        sa.CheckConstraint(
            "debit >= 0 AND credit >= 0",
            name="chk_journal_line_non_negative",
        ),
    )
    op.create_index("ix_journal_lines_entry_id", "journal_lines", ["entry_id"])
    op.create_index("ix_journal_lines_account_id", "journal_lines", ["account_id"])

    # 4. meetings
    op.create_table(
        "meetings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shg_id", sa.Uuid(), nullable=False),
        sa.Column("meeting_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="SCHEDULED", nullable=False),
        sa.Column("agenda", sa.Text(), nullable=True),
        sa.Column("minutes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shg_id"], ["shgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meetings_shg_id", "meetings", ["shg_id"])
    op.create_index("ix_meetings_meeting_date", "meetings", ["meeting_date"])
    op.create_index("ix_meetings_status", "meetings", ["status"])

    # 5. attendance
    op.create_table(
        "attendance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="PRESENT", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "member_id", name="uq_attendance_meeting_member"),
    )
    op.create_index("ix_attendance_meeting_id", "attendance", ["meeting_id"])
    op.create_index("ix_attendance_member_id", "attendance", ["member_id"])

    # 6. savings_dues
    op.create_table(
        "savings_dues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shg_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("amount_due", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(precision=14, scale=2), server_default="0.00", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="PENDING", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shg_id"], ["shgs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id", "period", name="uq_savings_dues_member_period"),
    )
    op.create_index("ix_savings_dues_shg_id", "savings_dues", ["shg_id"])
    op.create_index("ix_savings_dues_member_id", "savings_dues", ["member_id"])
    op.create_index("ix_savings_dues_period", "savings_dues", ["period"])
    op.create_index("ix_savings_dues_status", "savings_dues", ["status"])

    # 7. idempotency_keys
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_keys_scope_key"),
    )
    op.create_index("ix_idempotency_keys_key", "idempotency_keys", ["key"])
    op.create_index("ix_idempotency_keys_scope", "idempotency_keys", ["scope"])
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])

    # Database Triggers for Append-Only Enforcement
    if "postgres" in dialect:
        op.execute("""
        CREATE OR REPLACE FUNCTION prevent_ledger_table_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Ledger tables are append-only. UPDATE and DELETE are prohibited.';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_no_update_journal_entries BEFORE UPDATE ON journal_entries
        FOR EACH ROW EXECUTE FUNCTION prevent_ledger_table_mutation();

        CREATE TRIGGER trg_no_delete_journal_entries BEFORE DELETE ON journal_entries
        FOR EACH ROW EXECUTE FUNCTION prevent_ledger_table_mutation();

        CREATE TRIGGER trg_no_update_journal_lines BEFORE UPDATE ON journal_lines
        FOR EACH ROW EXECUTE FUNCTION prevent_ledger_table_mutation();

        CREATE TRIGGER trg_no_delete_journal_lines BEFORE DELETE ON journal_lines
        FOR EACH ROW EXECUTE FUNCTION prevent_ledger_table_mutation();
        """)
    elif "sqlite" in dialect:
        op.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_no_update_journal_entries
        BEFORE UPDATE ON journal_entries
        BEGIN
            SELECT RAISE(ABORT, 'journal_entries is append-only. UPDATE prohibited.');
        END;
        """)
        op.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_no_delete_journal_entries
        BEFORE DELETE ON journal_entries
        BEGIN
            SELECT RAISE(ABORT, 'journal_entries is append-only. DELETE prohibited.');
        END;
        """)
        op.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_no_update_journal_lines
        BEFORE UPDATE ON journal_lines
        BEGIN
            SELECT RAISE(ABORT, 'journal_lines is append-only. UPDATE prohibited.');
        END;
        """)
        op.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_no_delete_journal_lines
        BEFORE DELETE ON journal_lines
        BEGIN
            SELECT RAISE(ABORT, 'journal_lines is append-only. DELETE prohibited.');
        END;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if "postgres" in dialect:
        op.execute("DROP TRIGGER IF EXISTS trg_no_update_journal_entries ON journal_entries;")
        op.execute("DROP TRIGGER IF EXISTS trg_no_delete_journal_entries ON journal_entries;")
        op.execute("DROP TRIGGER IF EXISTS trg_no_update_journal_lines ON journal_lines;")
        op.execute("DROP TRIGGER IF EXISTS trg_no_delete_journal_lines ON journal_lines;")
        op.execute("DROP FUNCTION IF EXISTS prevent_ledger_table_mutation;")
    elif "sqlite" in dialect:
        op.execute("DROP TRIGGER IF EXISTS trg_no_update_journal_entries;")
        op.execute("DROP TRIGGER IF EXISTS trg_no_delete_journal_entries;")
        op.execute("DROP TRIGGER IF EXISTS trg_no_update_journal_lines;")
        op.execute("DROP TRIGGER IF EXISTS trg_no_delete_journal_lines;")

    op.drop_table("idempotency_keys")
    op.drop_table("savings_dues")
    op.drop_table("attendance")
    op.drop_table("meetings")
    op.drop_table("journal_lines")
    op.drop_table("journal_entries")
    op.drop_table("accounts")
