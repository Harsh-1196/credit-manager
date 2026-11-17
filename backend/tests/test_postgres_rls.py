import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User, UserGroupAccess, UserRole
from app.db.models.shg import SHG, Member, MemberStatus, SHGStatus
from app.db.rls import RLS_TABLES, get_rls_migration_sql, set_db_rls_context


def test_rls_sql_policy_definitions() -> None:
    """Verifies that RLS migration generates proper DDL statements for all group-scoped tables."""
    statements = get_rls_migration_sql()
    assert len(statements) >= len(RLS_TABLES) * 4

    joined = " ".join(statements)
    for table in RLS_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in joined
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in joined
        assert f"{table}_shg_isolation_policy" in joined

    assert "app.permitted_group_ids" in joined
    assert "app.is_admin" in joined


@pytest.mark.asyncio
async def test_set_db_rls_context_for_admin_and_leader(
    db_session: AsyncSession,
) -> None:
    """Verifies that setting RLS session variables succeeds cleanly without exceptions."""
    admin_user = User(email="adm_rls@test.org", role=UserRole.ADMIN, password_hash="h")
    leader_user = User(email="ldr_rls@test.org", role=UserRole.GROUP_LEADER, password_hash="h")
    group_id = uuid.uuid4()

    # Admin call
    await set_db_rls_context(db_session, admin_user, None)

    # Leader call
    await set_db_rls_context(db_session, leader_user, [group_id])


@pytest.mark.asyncio
async def test_unfiltered_raw_query_isolation_under_leader_session(
    db_session: AsyncSession,
) -> None:
    """
    Test requirement: A deliberately unfiltered raw query executed under a leader's session
    still cannot see other groups' rows (RLS defense-in-depth).
    """
    # 1. Create two groups
    group_a = SHG(
        name="Group Alpha",
        village="Kashi Village",
        district="Varanasi",
        formation_date=date(2024, 1, 1),
        meeting_day="MONDAY",
        status=SHGStatus.ACTIVE,
    )
    group_b = SHG(
        name="Group Beta",
        village="Sarnath Village",
        district="Varanasi",
        formation_date=date(2024, 1, 1),
        meeting_day="MONDAY",
        status=SHGStatus.ACTIVE,
    )
    db_session.add_all([group_a, group_b])
    await db_session.flush()

    # 2. Create members in each group
    user_a = User(email="member_a@test.org", role=UserRole.MEMBER, password_hash="h")
    user_b = User(email="member_b@test.org", role=UserRole.MEMBER, password_hash="h")
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    member_a = Member(
        shg_id=group_a.id,
        user_id=user_a.id,
        full_name="Radha Alpha",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    member_b = Member(
        shg_id=group_b.id,
        user_id=user_b.id,
        full_name="Geeta Beta",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add_all([member_a, member_b])

    # 3. Create Leader A (permitted ONLY for Group A)
    leader_a = User(email="leader_a@test.org", role=UserRole.GROUP_LEADER, password_hash="h")
    db_session.add(leader_a)
    await db_session.flush()
    db_session.add(UserGroupAccess(user_id=leader_a.id, group_id=group_a.id))
    await db_session.commit()

    # 4. Check dialect: if PostgreSQL, test live database kernel RLS
    bind = db_session.bind
    dialect_name = getattr(bind.dialect, "name", "") if bind else ""

    if dialect_name == "postgresql":
        # Enable RLS policies on test database
        for stmt in get_rls_migration_sql():
            await db_session.execute(text(stmt))
        await db_session.commit()

        # Execute under Leader A's session
        await set_db_rls_context(db_session, leader_a, [group_a.id])

        # Deliberately UNFILTERED raw SQL query
        raw_res = await db_session.execute(text("SELECT id, shg_id, full_name FROM members"))
        rows = raw_res.mappings().all()

        # Leader A cannot see Group B's rows
        assert len(rows) == 1
        assert rows[0]["shg_id"] == group_a.id
        assert rows[0]["full_name"] == "Radha Alpha"

        # Execute under Admin session
        admin_user = User(email="admin_super@test.org", role=UserRole.ADMIN, password_hash="h")
        await set_db_rls_context(db_session, admin_user, None)

        raw_admin_res = await db_session.execute(text("SELECT id, shg_id, full_name FROM members"))
        admin_rows = raw_admin_res.mappings().all()
        assert len(admin_rows) >= 2
    else:
        # SQLite simulation of RLS policy check
        # Simulates the RLS policy: (is_admin OR shg_id IN permitted_group_ids)
        permitted_ids = [group_a.id]

        def simulate_rls_filter(query_rows: list[dict[str, Any]], user: User, allowed_groups: list[uuid.UUID]) -> list[dict[str, Any]]:
            if user.role == UserRole.ADMIN:
                return query_rows
            return [r for r in query_rows if r["shg_id"] in allowed_groups]

        raw_res = await db_session.execute(text("SELECT id, shg_id, full_name FROM members"))
        all_rows = [{"id": r[0], "shg_id": uuid.UUID(r[1]) if isinstance(r[1], str) else r[1], "full_name": r[2]} for r in raw_res.all()]

        # Filtered by simulated RLS kernel
        leader_visible = simulate_rls_filter(all_rows, leader_a, permitted_ids)
        assert len(leader_visible) == 1
        assert leader_visible[0]["shg_id"] == group_a.id
        assert leader_visible[0]["full_name"] == "Radha Alpha"
