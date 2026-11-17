"""Phase 5 PostgreSQL Row-Level Security (RLS) policies

Revision ID: 0007_phase5_postgres_rls
Revises: 0006_phase5_outbox_readmodel
Create Date: 2026-11-17 13:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_phase5_postgres_rls"
down_revision: str | None = "0006_phase5_outbox_readmodel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = [
    "members",
    "loans",
    "savings_dues",
    "meetings",
    "accounts",
    "journal_entries",
]


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    for table in RLS_TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_shg_isolation_policy ON {table};"))
        conn.execute(sa.text(f"""
            CREATE POLICY {table}_shg_isolation_policy ON {table}
            AS PERMISSIVE
            FOR ALL
            TO PUBLIC
            USING (
                current_setting('app.is_admin', true) = 'true'
                OR
                shg_id::text = ANY(string_to_array(NULLIF(current_setting('app.permitted_group_ids', true), ''), ','))
            )
            WITH CHECK (
                current_setting('app.is_admin', true) = 'true'
                OR
                shg_id::text = ANY(string_to_array(NULLIF(current_setting('app.permitted_group_ids', true), ''), ','))
            );
        """))


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    for table in RLS_TABLES:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_shg_isolation_policy ON {table};"))
        conn.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;"))
        conn.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"))
