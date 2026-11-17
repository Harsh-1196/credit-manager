from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.models.auth import User, UserGroupAccess, UserRole
from app.db.models.ledger import JournalEntry
from app.db.models.meetings import Meeting, MeetingStatus
from app.db.models.platform import AuditLog
from app.db.models.shg import SHG, GroupSettings, InterestType, Member, MemberStatus
from app.domain.ledger.accounts import initialize_shg_chart_of_accounts


@pytest.fixture
async def setup_ai_data(db_session: AsyncSession):
    # Group A
    shg_a = SHG(
        id=uuid.uuid4(),
        name="Udaan Mahila Mandal",
        village="Rampur",
        district="Varanasi",
        formation_date=date(2025, 1, 1),
        meeting_day="MONDAY",
        meeting_frequency="MONTHLY",
        status="ACTIVE",
    )
    # Group B (Unassigned to Group A leader)
    shg_b = SHG(
        id=uuid.uuid4(),
        name="Pragati Mandal",
        village="Kashi",
        district="Varanasi",
        formation_date=date(2025, 1, 1),
        meeting_day="WEDNESDAY",
        meeting_frequency="MONTHLY",
        status="ACTIVE",
    )
    db_session.add_all([shg_a, shg_b])
    await db_session.flush()

    # Settings
    set_a = GroupSettings(
        shg_id=shg_a.id,
        monthly_saving_amount=Decimal("500.00"),
        late_fine_per_day=Decimal("5.00"),
        fine_grace_days=5,
        default_interest_rate=Decimal("12.000"),
        interest_type=InterestType.REDUCING,
    )
    db_session.add(set_a)
    await initialize_shg_chart_of_accounts(db_session, shg_a.id)
    await initialize_shg_chart_of_accounts(db_session, shg_b.id)

    # Users
    admin_user = User(
        id=uuid.uuid4(),
        email="admin_ai@shg.org",
        password_hash="pw",
        role=UserRole.ADMIN,
        is_active=True,
    )
    leader_a = User(
        id=uuid.uuid4(),
        email="leader_a@shg.org",
        password_hash="pw",
        role=UserRole.GROUP_LEADER,
        is_active=True,
    )
    member_user_1 = User(
        id=uuid.uuid4(),
        email="radha_ai@shg.org",
        password_hash="pw",
        role=UserRole.MEMBER,
        is_active=True,
    )
    member_user_2 = User(
        id=uuid.uuid4(),
        email="sunita_ai@shg.org",
        password_hash="pw",
        role=UserRole.MEMBER,
        is_active=True,
    )
    db_session.add_all([admin_user, leader_a, member_user_1, member_user_2])
    await db_session.flush()

    # Access scoping
    db_session.add(UserGroupAccess(user_id=leader_a.id, group_id=shg_a.id, access_level="LEADER"))
    db_session.add(UserGroupAccess(user_id=member_user_1.id, group_id=shg_a.id, access_level="MEMBER"))
    db_session.add(UserGroupAccess(user_id=member_user_2.id, group_id=shg_a.id, access_level="MEMBER"))

    # Members in Group A
    radha = Member(
        id=uuid.uuid4(),
        shg_id=shg_a.id,
        user_id=member_user_1.id,
        full_name="Radha Devi",
        phone="9876543210",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    sunita = Member(
        id=uuid.uuid4(),
        shg_id=shg_a.id,
        user_id=member_user_2.id,
        full_name="Sunita Devi",
        phone="9876543211",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    meera = Member(
        id=uuid.uuid4(),
        shg_id=shg_a.id,
        user_id=None,
        full_name="Meera Bai",
        phone="9876543212",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add_all([radha, sunita, meera])

    meeting_a = Meeting(
        id=uuid.uuid4(),
        shg_id=shg_a.id,
        meeting_date=date(2026, 3, 10),
        status=MeetingStatus.SCHEDULED,
        agenda="Monthly meeting collection",
    )
    db_session.add(meeting_a)

    await db_session.commit()

    return {
        "shg_a": shg_a,
        "shg_b": shg_b,
        "admin": admin_user,
        "leader_a": leader_a,
        "member_1": member_user_1,
        "member_2": member_user_2,
        "radha": radha,
        "sunita": sunita,
        "meera": meera,
        "meeting_a": meeting_a,
    }


@pytest.mark.asyncio
async def test_ai_chat_json_response_and_tool_execution(client: AsyncClient, setup_ai_data):
    data = setup_ai_data
    leader = data["leader_a"]
    shg_a = data["shg_a"]
    token = create_access_token(leader.id, leader.role.value)

    # Ask for dashboard summary
    payload = {
        "messages": [
            {"role": "user", "content": "What is our group corpus and savings on the dashboard?"}
        ],
        "shg_id": str(shg_a.id),
    }

    res = await client.post(
        "/api/v1/ai/chat",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        json=payload,
    )
    assert res.status_code == 200
    body = res.json()
    assert "content" in body
    assert len(body["tool_calls"]) > 0
    assert body["tool_calls"][0]["name"] == "get_group_dashboard"
    assert body["tool_calls"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_ai_chat_streaming_sse_response(client: AsyncClient, setup_ai_data):
    data = setup_ai_data
    leader = data["leader_a"]
    shg_a = data["shg_a"]
    token = create_access_token(leader.id, leader.role.value)

    payload = {
        "messages": [
            {"role": "user", "content": "Fetch collection sheet for meeting"}
        ],
        "shg_id": str(shg_a.id),
    }

    res = await client.post(
        "/api/v1/ai/chat",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
        },
        json=payload,
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    text = res.text
    assert "data:" in text
    assert '"type": "done"' in text


@pytest.mark.asyncio
async def test_ai_tool_scope_violation_safety(client: AsyncClient, setup_ai_data):
    data = setup_ai_data
    leader_a = data["leader_a"]
    shg_b = data["shg_b"]
    token = create_access_token(leader_a.id, leader_a.role.value)

    # Leader of A attempts to check overdue of Group B
    payload = {
        "messages": [
            {"role": "user", "content": f"Who is overdue in group {shg_b.id}?"}
        ],
    }

    res = await client.post(
        "/api/v1/ai/chat",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        json=payload,
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["tool_calls"]) > 0
    # Must fail safely with error status / 404
    tc = body["tool_calls"][0]
    assert tc["status"] == "error"
    assert "Resource not found" in tc["result_summary"] or "Failed" in tc["result_summary"]


@pytest.mark.asyncio
async def test_ai_draft_collection_extracts_amounts_without_db_writes(
    client: AsyncClient, setup_ai_data, db_session: AsyncSession
):
    data = setup_ai_data
    leader = data["leader_a"]
    meeting_a = data["meeting_a"]
    token = create_access_token(leader.id, leader.role.value)

    # Count journal entries before draft
    stmt_before = select(JournalEntry)
    res_before = await db_session.execute(stmt_before)
    entries_before = len(res_before.scalars().all())

    # Dictated notes with exact and ambiguous names
    notes = (
        "Radha paid 500 savings and 1100 emi. "
        "Meera gave 500 saving. "
        "Unknown Kamla gave 500. "
        "Devi paid 1000."
    )

    req_payload = {
        "meeting_id": str(meeting_a.id),
        "notes": notes,
    }

    res = await client.post(
        "/api/v1/ai/draft-collection",
        headers={"Authorization": f"Bearer {token}"},
        json=req_payload,
    )
    assert res.status_code == 200
    draft = res.json()

    assert draft["meeting_id"] == str(meeting_a.id)
    assert len(draft["items"]) >= 3

    # Radha matched
    radha_item = next(i for i in draft["items"] if i["member_name"] == "Radha Devi")
    assert Decimal(str(radha_item["savings_amount"])) == Decimal("500.00")
    assert Decimal(str(radha_item["loan_repayment_amount"])) == Decimal("1100.00")
    assert Decimal(str(radha_item["total_amount"])) == Decimal("1600.00")

    # Unmatched Kamla flagged without guessing
    assert len(draft["unmatched_items"]) >= 1
    unmatched_kamla = next((u for u in draft["unmatched_items"] if "Kamla" in u["raw_text"]), None)
    assert unmatched_kamla is not None
    assert unmatched_kamla["reason"] == "UNMATCHED_MEMBER"

    # Ambiguous Devi flagged without guessing
    ambiguous_devi = next((u for u in draft["unmatched_items"] if "Devi" in u["raw_text"]), None)
    assert ambiguous_devi is not None
    assert ambiguous_devi["reason"] == "AMBIGUOUS_MATCH"
    assert "Radha Devi" in ambiguous_devi["candidate_names"]
    assert "Sunita Devi" in ambiguous_devi["candidate_names"]

    # CRITICAL: Verify nothing was written to the ledger tables
    stmt_after = select(JournalEntry)
    res_after = await db_session.execute(stmt_after)
    entries_after = len(res_after.scalars().all())
    assert entries_after == entries_before, "Draft collection must NEVER write to ledger tables!"


@pytest.mark.asyncio
async def test_ai_audit_logging_no_pii(client: AsyncClient, setup_ai_data, db_session: AsyncSession):
    data = setup_ai_data
    leader = data["leader_a"]
    meeting_a = data["meeting_a"]
    token = create_access_token(leader.id, leader.role.value)

    res = await client.post(
        "/api/v1/ai/draft-collection",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "meeting_id": str(meeting_a.id),
            "notes": "Radha paid 500.",
        },
    )
    assert res.status_code == 200

    # Verify audit log was created
    stmt = (
        select(AuditLog)
        .where(AuditLog.action == "AI_DRAFT_COLLECTION")
        .order_by(AuditLog.occurred_at.desc())
    )
    audit_res = await db_session.execute(stmt)
    log_entry = audit_res.scalar_one_or_none()
    assert log_entry is not None
    assert log_entry.actor_id == leader.id
    # Assert after payload contains no unmasked PII
    after_payload = log_entry.after
    assert after_payload is not None
    assert "phone" not in after_payload
    assert "notes_length" in after_payload
