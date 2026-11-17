import time
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import quantize_money
from app.db.models.ledger import JournalEntry
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.meetings import Attendance, AttendanceStatus, Meeting, MeetingStatus
from app.db.models.savings import SavingsDue, SavingsDueStatus
from app.db.models.shg import SHG, Member, MemberStatus
from app.domain.loans.schedule import calculate_loan_schedule


@pytest.fixture
async def meeting_setup(
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_headers: dict[str, str],
) -> dict:
    shg: SHG = funded_group_fixture["shg"]

    # Enroll 5 members for standard tests
    members: list[Member] = []
    for i in range(1, 6):
        m = Member(
            shg_id=shg.id,
            full_name=f"Member {i:02d}",
            phone=f"+9198765432{i:02d}",
            joined_on=date(2025, 1, 1),
            status=MemberStatus.ACTIVE,
        )
        db_session.add(m)
        members.append(m)
    await db_session.commit()
    for m in members:
        await db_session.refresh(m)

    # Schedule a meeting
    meeting = Meeting(
        shg_id=shg.id,
        meeting_date=date(2026, 3, 15),
        status=MeetingStatus.SCHEDULED,
        agenda="March 2026 Regular Assembly & Collections",
    )
    db_session.add(meeting)

    # Setup a SavingsDue for period 2026-03 for member 1 & 2
    due1 = SavingsDue(
        shg_id=shg.id,
        member_id=members[0].id,
        period="2026-03",
        amount_due=Decimal("200.00"),
        amount_paid=Decimal("0.00"),
        status=SavingsDueStatus.PENDING,
    )
    due2 = SavingsDue(
        shg_id=shg.id,
        member_id=members[1].id,
        period="2026-03",
        amount_due=Decimal("200.00"),
        amount_paid=Decimal("0.00"),
        status=SavingsDueStatus.PENDING,
    )
    db_session.add_all([due1, due2])

    # Setup an active loan with schedule for member 1
    loan1 = Loan(
        shg_id=shg.id,
        member_id=members[0].id,
        loan_number="LN-TEST-0001",
        purpose="Livestock",
        principal=Decimal("12000.00"),
        interest_rate=Decimal("12.000"),
        interest_type="REDUCING",
        tenure_months=12,
        processing_fee=Decimal("120.00"),
        status=LoanStatus.ACTIVE,
        applied_by=funded_group_fixture["leader"].id,
        applied_at=date(2026, 1, 1),
        approved_by=funded_group_fixture["leader"].id,
        approved_at=date(2026, 1, 2),
        disbursed_at=date(2026, 1, 3),
        first_due_date=date(2026, 2, 15),
    )
    db_session.add(loan1)
    await db_session.flush()

    sched_plan = calculate_loan_schedule(
        principal=loan1.principal,
        annual_rate=loan1.interest_rate,
        interest_type=loan1.interest_type,
        tenure_months=loan1.tenure_months,
        first_due_date=date(2026, 2, 15),
    )
    for item in sched_plan.installments:
        sched_row = LoanSchedule(
            loan_id=loan1.id,
            installment_no=item.installment_no,
            due_date=item.due_date,
            principal_due=item.principal_due,
            interest_due=item.interest_due,
            total_due=item.total_due,
            principal_paid=Decimal("0.00"),
            interest_paid=Decimal("0.00"),
            penalty_paid=Decimal("0.00"),
            penalty_due=Decimal("0.00"),
            status=LoanScheduleStatus.PENDING,
        )
        db_session.add(sched_row)

    await db_session.commit()
    await db_session.refresh(meeting)
    await db_session.refresh(loan1)

    return {
        "shg": shg,
        "meeting": meeting,
        "members": members,
        "loan1": loan1,
        "admin_headers": admin_headers,
    }


@pytest.mark.asyncio
async def test_get_collection_sheet(client: AsyncClient, meeting_setup: dict):
    meeting = meeting_setup["meeting"]
    headers = meeting_setup["admin_headers"]

    resp = await client.get(f"/api/v1/meetings/{meeting.id}/collection-sheet", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["meeting_id"] == str(meeting.id)
    assert len(data["members"]) >= 5
    assert "totals" in data
    assert Decimal(data["totals"]["total_savings_due"]) > Decimal("0.00")

    # Member 1 has active loan
    m1_row = next(r for r in data["members"] if r["member_id"] == str(meeting_setup["members"][0].id))
    assert m1_row["active_loan_id"] == str(meeting_setup["loan1"].id)
    assert Decimal(m1_row["emi_due"]) > Decimal("0.00")

    # Verify alias endpoint /reports/collection-sheet/{meeting_id}
    alias_resp = await client.get(f"/api/v1/reports/collection-sheet/{meeting.id}", headers=headers)
    assert alias_resp.status_code == 200
    assert alias_resp.json()["meeting_id"] == str(meeting.id)


@pytest.mark.asyncio
async def test_batch_collections_all_or_nothing_failure_rule(
    client: AsyncClient,
    db_session: AsyncSession,
    meeting_setup: dict,
):
    """
    If any member collection fails validation (e.g. invalid member ID or loan repayment
    specified for a member with NO active loan), entire transaction rolls back.
    """
    meeting = meeting_setup["meeting"]
    headers = meeting_setup["admin_headers"]
    members = meeting_setup["members"]

    # Member 2 has NO active loan, but loan_repayment_amount is specified
    payload = {
        "period": "2026-03",
        "idempotency_key": str(uuid.uuid4()),
        "collections": [
            {
                "member_id": str(members[0].id),
                "attendance_status": "PRESENT",
                "savings_amount": "200.00",
                "loan_repayment_amount": "1000.00",
                "fine_amount": "0.00",
            },
            {
                "member_id": str(members[1].id),
                "attendance_status": "PRESENT",
                "savings_amount": "200.00",
                "loan_repayment_amount": "500.00",  # INVALID: Member 2 has no loan!
                "fine_amount": "0.00",
            },
        ],
    }

    resp = await client.post(f"/api/v1/meetings/{meeting.id}/collections", json=payload, headers=headers)
    assert resp.status_code == 400
    err = resp.json()
    assert err["code"] == "NO_ACTIVE_LOAN"

    # Verify ALL-OR-NOTHING: ZERO journal entries posted for this meeting
    entries_stmt = select(JournalEntry).where(JournalEntry.source_id == meeting.id)
    entries_res = await db_session.execute(entries_stmt)
    assert len(entries_res.scalars().all()) == 0

    # Verify meeting status remained SCHEDULED
    await db_session.refresh(meeting)
    assert meeting.status == MeetingStatus.SCHEDULED


@pytest.mark.asyncio
async def test_batch_collections_one_journal_entry_per_member_each_balanced(
    client: AsyncClient,
    db_session: AsyncSession,
    meeting_setup: dict,
):
    """
    SPEC Phase 4: One balanced journal entry per member per collection.
    Sum(debit) == Sum(credit) strictly holds for every entry.
    """
    meeting = meeting_setup["meeting"]
    headers = meeting_setup["admin_headers"]
    members = meeting_setup["members"]

    payload = {
        "period": "2026-03",
        "idempotency_key": str(uuid.uuid4()),
        "collections": [
            {
                "member_id": str(members[0].id),
                "attendance_status": "PRESENT",
                "savings_amount": "200.00",
                "loan_repayment_amount": "1066.19",
                "fine_amount": "20.00",
            },
            {
                "member_id": str(members[1].id),
                "attendance_status": "PRESENT",
                "savings_amount": "200.00",
                "loan_repayment_amount": "0.00",
                "fine_amount": "0.00",
            },
            {
                "member_id": str(members[2].id),
                "attendance_status": "ABSENT",
                "savings_amount": "0.00",
                "loan_repayment_amount": "0.00",
                "fine_amount": "0.00",
            },
        ],
    }

    resp = await client.post(f"/api/v1/meetings/{meeting.id}/collections", json=payload, headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["members_count"] == 2  # Members 0 and 1 contributed
    assert body["journal_entries_count"] == 2
    assert len(body["journal_entry_ids"]) == 2
    assert body["meeting_status"] == "HELD"

    # Verify the journal entries in the database
    for entry_id in body["journal_entry_ids"]:
        entry_stmt = select(JournalEntry).where(JournalEntry.id == uuid.UUID(entry_id))
        entry_res = await db_session.execute(entry_stmt)
        entry = entry_res.scalar_one()

        tot_debit = Decimal("0.00")
        tot_credit = Decimal("0.00")
        for line in entry.lines:
            tot_debit += line.debit
            tot_credit += line.credit

        # Exact balanced double entry
        assert quantize_money(tot_debit) == quantize_money(tot_credit)

    # Verify meeting status is now HELD
    await db_session.refresh(meeting)
    assert meeting.status == MeetingStatus.HELD


@pytest.mark.asyncio
async def test_batch_collections_idempotency_replay_and_conflict(
    client: AsyncClient,
    meeting_setup: dict,
):
    meeting = meeting_setup["meeting"]
    headers = meeting_setup["admin_headers"]
    members = meeting_setup["members"]

    idem_key = f"idem-meeting-{uuid.uuid4()}"
    payload1 = {
        "period": "2026-03",
        "idempotency_key": idem_key,
        "collections": [
            {
                "member_id": str(members[0].id),
                "attendance_status": "PRESENT",
                "savings_amount": "200.00",
                "loan_repayment_amount": "0.00",
                "fine_amount": "0.00",
            }
        ],
    }

    # First request
    resp1 = await client.post(f"/api/v1/meetings/{meeting.id}/collections", json=payload1, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Replay with same key and same body: returns identical cached response
    resp2 = await client.post(f"/api/v1/meetings/{meeting.id}/collections", json=payload1, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json() == data1

    # Same key with different body: 409 Conflict
    payload_diff = dict(payload1)
    payload_diff["collections"] = [
        {
            "member_id": str(members[0].id),
            "attendance_status": "PRESENT",
            "savings_amount": "300.00",  # Different!
            "loan_repayment_amount": "0.00",
            "fine_amount": "0.00",
        }
    ]
    resp3 = await client.post(f"/api/v1/meetings/{meeting.id}/collections", json=payload_diff, headers=headers)
    assert resp3.status_code == 409


@pytest.mark.asyncio
async def test_member_attendance_history_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    meeting_setup: dict,
):
    meeting = meeting_setup["meeting"]
    headers = meeting_setup["admin_headers"]
    member = meeting_setup["members"][0]

    # Record attendance
    att = Attendance(
        meeting_id=meeting.id,
        member_id=member.id,
        status=AttendanceStatus.PRESENT,
    )
    db_session.add(att)
    await db_session.commit()

    resp = await client.get(f"/api/v1/members/{member.id}/attendance", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["member_id"] == str(member.id)
    assert data["summary"]["total_meetings"] >= 1
    assert data["summary"]["present_count"] >= 1
    assert len(data["records"]) >= 1
    assert data["records"][0]["status"] == "PRESENT"


@pytest.mark.asyncio
async def test_20_member_batch_collection_performance_benchmark(
    client: AsyncClient,
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_headers: dict[str, str],
):
    """
    SPEC Phase 4 requirement:
    'Performance: a 20-member batch completes in under 1 second.
    Add a test or benchmark and record the result in docs/metrics.md.'
    """
    shg: SHG = funded_group_fixture["shg"]
    headers: dict[str, str] = admin_headers

    # 1. Setup 20 active members
    benchmark_members: list[Member] = []
    for i in range(1, 21):
        m = Member(
            shg_id=shg.id,
            full_name=f"Perf Member {i:02d}",
            phone=f"+9191000000{i:02d}",
            joined_on=date(2025, 1, 1),
            status=MemberStatus.ACTIVE,
        )
        db_session.add(m)
        benchmark_members.append(m)
    await db_session.commit()

    # 2. Schedule meeting for performance test
    perf_meeting = Meeting(
        shg_id=shg.id,
        meeting_date=date(2026, 4, 15),
        status=MeetingStatus.SCHEDULED,
        agenda="20-Member Benchmark Assembly",
    )
    db_session.add(perf_meeting)

    # 3. Setup active loans for 10 members
    for i in range(10):
        m = benchmark_members[i]
        loan = Loan(
            shg_id=shg.id,
            member_id=m.id,
            loan_number=f"LN-PERF-{i+1:04d}",
            purpose="Small Enterprise",
            principal=Decimal("10000.00"),
            interest_rate=Decimal("12.000"),
            interest_type="REDUCING",
            tenure_months=10,
            processing_fee=Decimal("100.00"),
            status=LoanStatus.ACTIVE,
            applied_by=funded_group_fixture["leader"].id,
            applied_at=date(2026, 1, 1),
            approved_by=funded_group_fixture["leader"].id,
            approved_at=date(2026, 1, 2),
            disbursed_at=date(2026, 1, 3),
            first_due_date=date(2026, 2, 15),
        )
        db_session.add(loan)
        await db_session.flush()

        sched_plan = calculate_loan_schedule(
            principal=loan.principal,
            annual_rate=loan.interest_rate,
            interest_type=loan.interest_type,
            tenure_months=loan.tenure_months,
            first_due_date=date(2026, 2, 15),
        )
        for item in sched_plan.installments:
            sched_row = LoanSchedule(
                loan_id=loan.id,
                installment_no=item.installment_no,
                due_date=item.due_date,
                principal_due=item.principal_due,
                interest_due=item.interest_due,
                total_due=item.total_due,
                principal_paid=Decimal("0.00"),
                interest_paid=Decimal("0.00"),
                penalty_paid=Decimal("0.00"),
                penalty_due=Decimal("0.00"),
                status=LoanScheduleStatus.PENDING,
            )
            db_session.add(sched_row)

    await db_session.commit()
    await db_session.refresh(perf_meeting)

    # 4. Prepare 20-member batch collection request
    collections_payload = []
    for i, m in enumerate(benchmark_members):
        collections_payload.append(
            {
                "member_id": str(m.id),
                "attendance_status": "PRESENT" if i % 5 != 0 else "ABSENT",
                "savings_amount": "200.00",
                "loan_repayment_amount": "1055.82" if i < 10 else "0.00",
                "fine_amount": "10.00" if i % 4 == 0 else "0.00",
            }
        )

    batch_request = {
        "period": "2026-04",
        "idempotency_key": str(uuid.uuid4()),
        "collections": collections_payload,
    }

    # 5. Benchmark timing
    start_time = time.perf_counter()
    resp = await client.post(
        f"/api/v1/meetings/{perf_meeting.id}/collections",
        json=batch_request,
        headers=headers,
    )
    elapsed_time = time.perf_counter() - start_time

    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["members_count"] == 20
    assert res_data["journal_entries_count"] == 20

    print(f"\n[BENCHMARK] 20-member batch collection completed in {elapsed_time * 1000:.2f} ms")
    assert elapsed_time < 1.0, f"Benchmark failed: Took {elapsed_time:.3f}s (target < 1.0s)"
