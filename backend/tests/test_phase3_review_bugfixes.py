import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User
from app.db.models.ledger import JournalEntry, JournalLine
from app.db.models.loans import Loan, LoanSchedule, LoanStatus
from app.db.models.platform import AuditLog
from app.db.models.shg import SHG, InterestType, Member, MemberStatus
from app.domain.loans.allocation import allocate_repayment
from app.services.loans import disburse_loan, repay_loan


@pytest.mark.asyncio
async def test_full_loan_payoff_allocation_balanced(db_session: AsyncSession, funded_group_fixture: dict):
    """
    Bug 1 Fix Verification:
    When a borrower repays the total payoff amount (all remaining principal + interest),
    allocation must not leave unallocated funds or unbalanced ledger entries.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    # 1. Create and disburse 2-month loan: ₹2,000 principal at 12% flat
    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-PAYOFF-001",
        purpose="Livestock",
        principal=Decimal("2000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.FLAT,
        tenure_months=2,
        processing_fee=Decimal("0.00"),
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
    )
    db_session.add(loan)
    await db_session.commit()

    disbursed = await disburse_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
        first_due_date=date(2026, 1, 1),
    )
    await db_session.commit()
    await db_session.refresh(disbursed)

    # 2. Total payoff = ₹2,000 principal + ₹40 interest = ₹2,040.00
    total_principal = sum(s.principal_due for s in disbursed.schedule)
    total_interest = sum(s.interest_due for s in disbursed.schedule)
    payoff_amount = total_principal + total_interest

    # 3. Direct domain allocation check on copies to avoid in-memory mutation
    sched_copies = [
        LoanSchedule(
            installment_no=s.installment_no,
            due_date=s.due_date,
            principal_due=s.principal_due,
            interest_due=s.interest_due,
            total_due=s.total_due,
            principal_paid=s.principal_paid,
            interest_paid=s.interest_paid,
            penalty_paid=s.penalty_paid,
            penalty_due=s.penalty_due,
            status=s.status,
        )
        for s in disbursed.schedule
    ]
    alloc_res = allocate_repayment(
        loan=disbursed,
        schedule_items=sched_copies,
        payment_amount=payoff_amount,
        as_of_date=date(2026, 1, 1),
    )
    assert alloc_res.unallocated_amount == Decimal("0.00")
    assert alloc_res.total_principal == total_principal
    assert alloc_res.total_interest == total_interest
    assert alloc_res.is_loan_fully_paid is True

    # 4. Service execution: repay full payoff amount
    updated_loan, service_alloc = await repay_loan(
        db=db_session,
        loan_id=disbursed.id,
        shg_id=shg.id,
        current_user=leader,
        amount=payoff_amount,
        payment_date=date(2026, 1, 1),
    )
    await db_session.commit()
    await db_session.refresh(updated_loan)

    assert updated_loan.status == LoanStatus.CLOSED
    assert service_alloc.is_loan_fully_paid is True

    # 5. Verify journal entry debit == credit exactly
    lines_stmt = (
        select(JournalLine)
        .join(JournalEntry)
        .where(JournalEntry.source_id == updated_loan.id, JournalEntry.source_type == "REPAYMENT")
    )
    lines_res = await db_session.execute(lines_stmt)
    repay_lines = list(lines_res.scalars().all())

    tot_debit = sum(line.debit for line in repay_lines)
    tot_credit = sum(line.credit for line in repay_lines)
    assert tot_debit == payoff_amount
    assert tot_credit == payoff_amount
    assert tot_debit == tot_credit


@pytest.mark.asyncio
async def test_auditor_cannot_create_or_submit_loan(
    client: AsyncClient,
    test_group: SHG,
    auditor_headers: dict[str, str],
    member_user: User,
):
    """
    Bug 5 Fix Verification:
    AUDITOR role must be strictly read-only and cannot create or submit loan applications (HTTP 403).
    """
    # 1. Auditor attempts to create loan
    payload = {
        "shg_id": str(test_group.id),
        "member_id": str(member_user.id),
        "purpose": "Auditor loan attempt",
        "principal": "5000.00",
        "interest_rate": "12.00",
        "interest_type": "REDUCING",
        "tenure_months": 6,
        "first_due_date": "2026-06-01",
    }
    create_res = await client.post("/api/v1/loans", headers=auditor_headers, json=payload)
    assert create_res.status_code == 403

    # 2. Auditor attempts to submit an existing draft loan
    submit_res = await client.post(f"/api/v1/loans/{uuid.uuid4()}/submit", headers=auditor_headers)
    assert submit_res.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_view_other_member_loan_history(
    client: AsyncClient,
    db_session: AsyncSession,
    test_group: SHG,
    leader_headers: dict[str, str],
    member_headers: dict[str, str],
    leader_user: User,
):
    """
    Bug 4 Fix Verification:
    MEMBER role must receive HTTP 404 when attempting to access another member's loan history.
    """
    # Create a member record not belonging to member_headers caller
    other_member = Member(
        shg_id=test_group.id,
        user_id=leader_user.id,
        full_name="Other Member",
        phone="9876543299",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(other_member)
    await db_session.flush()

    loan = Loan(
        shg_id=test_group.id,
        member_id=other_member.id,
        loan_number="LN-PRIV-001",
        purpose="Private purpose",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        status=LoanStatus.DRAFT,
        applied_by=leader_user.id,
    )
    db_session.add(loan)
    await db_session.commit()

    # Member requests history of other member's loan -> 404
    res = await client.get(f"/api/v1/loans/{loan.id}/history", headers=member_headers)
    assert res.status_code == 404

    # Leader requests history -> 200
    res_leader = await client.get(f"/api/v1/loans/{loan.id}/history", headers=leader_headers)
    assert res_leader.status_code == 200


@pytest.mark.asyncio
async def test_member_cannot_preview_other_member_repayment(
    client: AsyncClient,
    db_session: AsyncSession,
    test_group: SHG,
    member_headers: dict[str, str],
    leader_user: User,
):
    """
    Bug 4 Fix Verification:
    MEMBER role cannot preview repayment breakdown of another member's loan (returns 404).
    """
    other_member = Member(
        shg_id=test_group.id,
        user_id=leader_user.id,
        full_name="Other Member 2",
        phone="9876543298",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(other_member)
    await db_session.flush()

    loan = Loan(
        shg_id=test_group.id,
        member_id=other_member.id,
        loan_number="LN-PRIV-002",
        purpose="Private",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        status=LoanStatus.ACTIVE,
        applied_by=leader_user.id,
    )
    db_session.add(loan)
    await db_session.commit()

    res = await client.post(
        f"/api/v1/loans/{loan.id}/preview-repayment",
        headers=member_headers,
        json={"amount": "1000.00"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_member_or_auditor_cannot_view_disburse_preview(
    client: AsyncClient,
    db_session: AsyncSession,
    test_group: SHG,
    member_headers: dict[str, str],
    auditor_headers: dict[str, str],
    leader_headers: dict[str, str],
    leader_user: User,
):
    """
    Bug 5 Fix Verification:
    Only GROUP_LEADER or ADMIN can view disbursal preview and cash sufficiency.
    MEMBER and AUDITOR are forbidden (403).
    """
    other_member = Member(
        shg_id=test_group.id,
        user_id=leader_user.id,
        full_name="Member X",
        phone="9876543297",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(other_member)
    await db_session.flush()

    loan = Loan(
        shg_id=test_group.id,
        member_id=other_member.id,
        loan_number="LN-DISB-001",
        purpose="Disbursal test",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        status=LoanStatus.APPROVED,
        applied_by=leader_user.id,
    )
    db_session.add(loan)
    await db_session.commit()

    # Member -> 403
    res_m = await client.get(f"/api/v1/loans/{loan.id}/disburse-preview", headers=member_headers)
    assert res_m.status_code == 403

    # Auditor -> 403
    res_a = await client.get(f"/api/v1/loans/{loan.id}/disburse-preview", headers=auditor_headers)
    assert res_a.status_code == 403

    # Leader -> 200
    res_l = await client.get(f"/api/v1/loans/{loan.id}/disburse-preview", headers=leader_headers)
    assert res_l.status_code == 200


@pytest.mark.asyncio
async def test_portfolio_metrics_authorization_and_scoping(
    client: AsyncClient,
    admin_headers: dict[str, str],
    leader_headers: dict[str, str],
    auditor_headers: dict[str, str],
    member_headers: dict[str, str],
    test_group: SHG,
):
    """
    Bug 3 Fix Verification:
    - MEMBER cannot view portfolio metrics (403).
    - AUDITOR and LEADER without shg_id query are scoped to their assigned groups only.
    - ADMIN can view global portfolio metrics.
    """
    # 1. Member -> 403
    res_m = await client.get("/api/v1/loans/metrics/portfolio", headers=member_headers)
    assert res_m.status_code == 403

    # 2. Leader without shg_id -> 200 (scoped to permitted groups)
    res_l = await client.get("/api/v1/loans/metrics/portfolio", headers=leader_headers)
    assert res_l.status_code == 200

    # 3. Auditor without shg_id -> 200 (scoped to permitted groups)
    res_a = await client.get("/api/v1/loans/metrics/portfolio", headers=auditor_headers)
    assert res_a.status_code == 200

    # 4. Admin global -> 200
    res_adm = await client.get("/api/v1/loans/metrics/portfolio", headers=admin_headers)
    assert res_adm.status_code == 200


@pytest.mark.asyncio
async def test_loan_disbursal_idempotency_replay_and_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_headers: dict[str, str],
):
    """
    Bug 7 Fix Verification:
    Disbursal with same idempotency key returns cached response on replay.
    Same key with different payload returns 409 IDEMPOTENCY_CONFLICT.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-IDEM-DISB-001",
        purpose="Agri",
        principal=Decimal("4000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
        version=1,
    )
    db_session.add(loan)
    await db_session.commit()

    idem_key = f"idem-disb-{uuid.uuid4()}"
    payload1 = {"version": 1, "idempotency_key": idem_key}

    # 1. First disbursal
    res1 = await client.post(f"/api/v1/loans/{loan.id}/disburse", headers=admin_headers, json=payload1)
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["status"] in ["DISBURSED", "ACTIVE"]

    # 2. Replay with identical payload & key -> returns cached 200
    res2 = await client.post(f"/api/v1/loans/{loan.id}/disburse", headers=admin_headers, json=payload1)
    assert res2.status_code == 200
    assert res2.json() == body1

    # 3. Same key with different payload (e.g. different first_due_date) -> 409 Conflict
    payload_diff = {"version": 1, "first_due_date": "2026-09-01", "idempotency_key": idem_key}
    res3 = await client.post(f"/api/v1/loans/{loan.id}/disburse", headers=admin_headers, json=payload_diff)
    assert res3.status_code == 409
    assert res3.json()["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_loan_repayment_idempotency_replay_and_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_headers: dict[str, str],
):
    """
    Bug 7 Fix Verification:
    Repayment with same idempotency key returns cached response without duplicate postings.
    Same key with different amount returns 409 IDEMPOTENCY_CONFLICT.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-IDEM-REPAY-001",
        purpose="Weaving",
        principal=Decimal("6000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
    )
    db_session.add(loan)
    await db_session.commit()

    disbursed = await disburse_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
    )
    await db_session.commit()

    idem_key = f"idem-repay-{uuid.uuid4()}"
    payload1 = {"amount": "1000.00", "idempotency_key": idem_key}

    # 1. First repayment
    res1 = await client.post(f"/api/v1/loans/{disbursed.id}/repay", headers=admin_headers, json=payload1)
    assert res1.status_code == 200
    body1 = res1.json()

    # 2. Replay with identical key & payload -> returns cached 200
    res2 = await client.post(f"/api/v1/loans/{disbursed.id}/repay", headers=admin_headers, json=payload1)
    assert res2.status_code == 200
    assert res2.json() == body1

    # 3. Replay with same key but different amount -> 409 Conflict
    payload_diff = {"amount": "2000.00", "idempotency_key": idem_key}
    res3 = await client.post(f"/api/v1/loans/{disbursed.id}/repay", headers=admin_headers, json=payload_diff)
    assert res3.status_code == 409
    assert res3.json()["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_repayment_records_audit_log_row(
    client: AsyncClient,
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_headers: dict[str, str],
):
    """
    Bug 8 Fix Verification:
    Every loan repayment must explicitly write a LOAN_REPAYMENT row in the audit log.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    leader = fixture["leader"]
    member = fixture["member"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-AUDIT-001",
        purpose="Tailoring",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
    )
    db_session.add(loan)
    await db_session.commit()

    disbursed = await disburse_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
    )
    await db_session.commit()

    # Record partial repayment (status remains ACTIVE)
    res = await client.post(f"/api/v1/loans/{disbursed.id}/repay", headers=admin_headers, json={"amount": "500.00"})
    assert res.status_code == 200

    # Query audit log for LOAN_REPAYMENT
    audit_stmt = select(AuditLog).where(
        AuditLog.entity_id == str(disbursed.id),
        AuditLog.action == "LOAN_REPAYMENT",
    )
    audit_res = await db_session.execute(audit_stmt)
    audit_entry = audit_res.scalar_one_or_none()
    assert audit_entry is not None
    assert audit_entry.after["payment_amount"] == "500.00"


@pytest.mark.asyncio
async def test_spec_schedule_and_repayments_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    funded_group_fixture: dict,
    admin_headers: dict[str, str],
    leader_user: User,
):
    """
    SPEC Section 8 Endpoints Verification:
    - GET /loans/{id}/schedule returns schedule installments.
    - POST /loans/{id}/repayments processes repayments.
    """
    fixture = funded_group_fixture
    shg = fixture["shg"]
    member = fixture["member"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-SPEC-001",
        purpose="Seeds",
        principal=Decimal("3000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=3,
        status=LoanStatus.APPROVED,
        applied_by=leader_user.id,
    )
    db_session.add(loan)
    await db_session.commit()

    disbursed = await disburse_loan(db=db_session, loan_id=loan.id, shg_id=shg.id, current_user=leader_user)
    await db_session.commit()

    # 1. GET /loans/{id}/schedule
    sched_res = await client.get(f"/api/v1/loans/{disbursed.id}/schedule", headers=admin_headers)
    assert sched_res.status_code == 200
    installments = sched_res.json()
    assert len(installments) == 3
    assert installments[0]["installment_no"] == 1

    # 2. POST /loans/{id}/repayments
    repay_res = await client.post(
        f"/api/v1/loans/{disbursed.id}/repayments",
        headers=admin_headers,
        json={"amount": "1000.00"},
    )
    assert repay_res.status_code == 200
    assert repay_res.json()["loan_number"] == "LN-SPEC-001"
