import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_audit_log
from app.audit.verifier import verify_audit_chain
from app.db.models.platform import AuditLog


@pytest.mark.asyncio
async def test_mutation_writes_audit_log_and_chain_verifies(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    # Initial audit verification (may be 0 rows)
    res_initial = await verify_audit_chain(db_session)
    assert res_initial["valid"] is True
    initial_count = res_initial["count"]

    # Perform mutation: create a new group
    res = await client.post(
        "/api/v1/groups",
        headers=admin_headers,
        json={
            "name": "Audit Test Group",
            "village": "Audit Village",
            "district": "Audit District",
            "formation_date": "2025-01-01",
            "meeting_day": "Friday",
            "meeting_frequency": "MONTHLY",
        },
    )
    assert res.status_code == 201
    group_id = res.json()["id"]

    # Perform another mutation: update the group
    res2 = await client.patch(
        f"/api/v1/groups/{group_id}",
        headers=admin_headers,
        json={"name": "Audit Test Group Renamed"},
    )
    assert res2.status_code == 200

    # Verify audit entries were written
    res_after = await verify_audit_chain(db_session)
    assert res_after["valid"] is True
    assert res_after["count"] >= initial_count + 2
    assert res_after["error"] is None


@pytest.mark.asyncio
async def test_audit_chain_tamper_detection(
    db_session: AsyncSession,
) -> None:
    # 1. Create a series of chained audit logs
    for i in range(4):
        await record_audit_log(
            db=db_session,
            action=f"ACTION_{i}",
            entity_type="TestEntity",
            entity_id=f"id_{i}",
            after={"step": i, "status": "ok"},
        )
    await db_session.commit()

    # Verify chain is currently 100% valid
    res_before = await verify_audit_chain(db_session)
    assert res_before["valid"] is True
    assert res_before["count"] >= 4

    # 2. Tamper with the 2nd row's content directly in the database
    stmt = select(AuditLog).order_by(AuditLog.occurred_at.asc(), AuditLog.created_at.asc())
    rows = list((await db_session.execute(stmt)).scalars().all())
    target_row = rows[1]
    target_row.before = {"tampered": "illegal_modification"}
    await db_session.commit()

    # 3. Verify that verify_audit_chain catches the tamper and reports the broken link
    res_after = await verify_audit_chain(db_session)
    assert res_after["valid"] is False
    assert res_after["broken_at_index"] == 1
    assert "Tampered row at index 1" in res_after["error"]
