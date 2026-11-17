import uuid
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User, UserRole

# Core tables scoped to specific SHG groups
RLS_TABLES: Sequence[str] = [
    "members",
    "loans",
    "savings_dues",
    "meetings",
    "accounts",
    "journal_entries",
]


async def set_db_rls_context(
    db: AsyncSession,
    user: User,
    permitted_group_ids: list[uuid.UUID] | None = None,
) -> None:
    """
    Sets PostgreSQL session-local configuration variables for Row-Level Security (RLS).
    Uses SET LOCAL to strictly scope variables to the current transaction.
    Guarantees defense-in-depth: even if application code runs an unfiltered raw query,
    PostgreSQL's kernel enforces that rows from other groups cannot be selected or modified.
    """
    bind = db.bind
    dialect_name = getattr(bind.dialect, "name", "") if bind else ""

    if dialect_name != "postgresql":
        # SQLite or non-Postgres dialect fallback
        return

    is_admin_val = "true" if user.role == UserRole.ADMIN else "false"
    group_ids_str = ",".join(str(gid) for gid in (permitted_group_ids or []))

    # Escape parameters safely using SQLAlchemy text
    await db.execute(text("SET LOCAL app.is_admin = :admin_flag"), {"admin_flag": is_admin_val})
    await db.execute(text("SET LOCAL app.permitted_group_ids = :group_ids"), {"group_ids": group_ids_str})


def get_rls_migration_sql() -> list[str]:
    """Generates DDL statements to enable RLS and install isolation policies."""
    statements: list[str] = []

    for table in RLS_TABLES:
        statements.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        statements.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        statements.append(f"DROP POLICY IF EXISTS {table}_shg_isolation_policy ON {table};")
        statements.append(f"""
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
        """)

    return statements
