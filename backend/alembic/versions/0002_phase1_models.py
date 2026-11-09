"""Phase 1 models: users, refresh_tokens, user_group_access, shgs, group_settings, members, member_roles, audit_log

Revision ID: 0002_phase1_models
Revises: 0001_initial_empty
Create Date: 2026-11-09 17:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_phase1_models"
down_revision: str | None = "0001_initial_empty"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # 2. refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
    )
    op.create_index(op.f("ix_refresh_tokens_family_id"), "refresh_tokens", ["family_id"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    # 3. shgs
    op.create_table(
        "shgs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("village", sa.String(length=255), nullable=False),
        sa.Column("ward", sa.String(length=100), nullable=True),
        sa.Column("district", sa.String(length=255), nullable=False),
        sa.Column("formation_date", sa.Date(), nullable=False),
        sa.Column("meeting_day", sa.String(length=50), nullable=False),
        sa.Column("meeting_frequency", sa.String(length=50), server_default="MONTHLY", nullable=False),
        sa.Column("bank_account_label", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shgs")),
    )

    # 4. group_settings
    op.create_table(
        "group_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shg_id", sa.Uuid(), nullable=False),
        sa.Column("monthly_saving_amount", sa.Numeric(precision=14, scale=2), server_default="200.00", nullable=False),
        sa.Column("late_fine_per_day", sa.Numeric(precision=14, scale=2), server_default="5.00", nullable=False),
        sa.Column("fine_grace_days", sa.Integer(), server_default="5", nullable=False),
        sa.Column("default_interest_rate", sa.Numeric(precision=6, scale=3), server_default="12.000", nullable=False),
        sa.Column("interest_type", sa.String(length=50), server_default="REDUCING", nullable=False),
        sa.Column("max_loan_multiple", sa.Numeric(precision=6, scale=2), server_default="3.00", nullable=False),
        sa.Column("min_tenure_months", sa.Integer(), server_default="3", nullable=False),
        sa.Column("max_tenure_months", sa.Integer(), server_default="24", nullable=False),
        sa.Column("processing_fee_percent", sa.Numeric(precision=6, scale=3), server_default="1.000", nullable=False),
        sa.Column("penalty_interest_rate", sa.Numeric(precision=6, scale=3), server_default="2.000", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["shg_id"], ["shgs.id"], name=op.f("fk_group_settings_shg_id_shgs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group_settings")),
        sa.UniqueConstraint("shg_id", name=op.f("uq_group_settings_shg_id")),
    )

    # 5. user_group_access
    op.create_table(
        "user_group_access",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("access_level", sa.String(length=50), server_default="STANDARD", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["shgs.id"], name=op.f("fk_user_group_access_group_id_shgs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_group_access_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_group_access")),
    )
    op.create_index(op.f("ix_user_group_access_group_id"), "user_group_access", ["group_id"], unique=False)
    op.create_index(op.f("ix_user_group_access_user_id"), "user_group_access", ["user_id"], unique=False)

    # 6. members
    op.create_table(
        "members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shg_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("id_proof_type", sa.String(length=50), nullable=True),
        sa.Column("id_proof_last4", sa.String(length=4), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("joined_on", sa.Date(), nullable=False),
        sa.Column("exited_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shg_id"], ["shgs.id"], name=op.f("fk_members_shg_id_shgs"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_members_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_members")),
    )
    op.create_index(op.f("ix_members_shg_id"), "members", ["shg_id"], unique=False)
    op.create_index(op.f("ix_members_user_id"), "members", ["user_id"], unique=False)

    # 7. member_roles
    op.create_table(
        "member_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=50), server_default="MEMBER", nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name=op.f("fk_member_roles_member_id_members"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_roles")),
    )
    op.create_index(op.f("ix_member_roles_member_id"), "member_roles", ["member_id"], unique=False)

    # 8. audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(length=50), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_log_entity_id"), "audit_log", ["entity_id"], unique=False)
    op.create_index(op.f("ix_audit_log_entity_type"), "audit_log", ["entity_type"], unique=False)
    op.create_index(op.f("ix_audit_log_occurred_at"), "audit_log", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_audit_log_request_id"), "audit_log", ["request_id"], unique=False)
    op.create_index(op.f("ix_audit_log_row_hash"), "audit_log", ["row_hash"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("member_roles")
    op.drop_table("members")
    op.drop_table("user_group_access")
    op.drop_table("group_settings")
    op.drop_table("shgs")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
