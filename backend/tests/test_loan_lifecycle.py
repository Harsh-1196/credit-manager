import itertools
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.auth import User, UserGroupAccess, UserRole
from app.db.models.loans import Loan, LoanStatus
from app.db.models.shg import SHG, GroupSettings, InterestType, Member, MemberStatus, SHGStatus
from app.domain.loans.eligibility import evaluate_loan_eligibility
from app.domain.loans.state_machine import VALID_TRANSITIONS, LoanStateMachine


@pytest_asyncio.fixture
async def group_with_members(db_session: AsyncSession, admin_user: User):
    """Creates an active SHG, group settings, and two members."""
    shg = SHG(
        name="Pragati SHG",
        village="Rampur",
        district="Varanasi",
        formation_date=date(2024, 1, 1),
        meeting_day="MONDAY",
        meeting_frequency="MONTHLY",
        status=SHGStatus.ACTIVE,
    )
    db_session.add(shg)
    await db_session.flush()

    settings = GroupSettings(
        shg_id=shg.id,
        monthly_saving_amount=Decimal("500.00"),
        default_interest_rate=Decimal("12.000"),
        interest_type=InterestType.REDUCING,
        max_loan_multiple=Decimal("4.00"),
        min_tenure_months=1,
        max_tenure_months=36,
    )
    db_session.add(settings)

    # Member 1 with associated User (leader)
    leader_user = User(
        email="leader@pragati.org",
        password_hash="hash",
        phone="9876543210",
        role=UserRole.GROUP_LEADER,
    )
    db_session.add(leader_user)
    await db_session.flush()

    access_leader = UserGroupAccess(user_id=leader_user.id, group_id=shg.id)
    db_session.add(access_leader)

    member1 = Member(
        shg_id=shg.id,
        user_id=leader_user.id,
        full_name="Radha Devi",
        phone="9876543210",
        joined_on=date(2024, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(member1)

    # Member 2 (regular member with user)
    member_user = User(
        email="sunita@pragati.org",
        password_hash="hash",
        phone="9876543211",
        role=UserRole.MEMBER,
    )
    db_session.add(member_user)
    await db_session.flush()

    access_member = UserGroupAccess(user_id=member_user.id, group_id=shg.id)
    db_session.add(access_member)

    member2 = Member(
        shg_id=shg.id,
        user_id=member_user.id,
        full_name="Sunita Sharma",
        phone="9876543211",
        joined_on=date(2024, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(member2)

    # Leader 2 for testing maker-checker approval
    leader_user2 = User(
        email="leader2@pragati.org",
        password_hash="hash",
        phone="9876543212",
        role=UserRole.GROUP_LEADER,
    )
    db_session.add(leader_user2)
    await db_session.flush()
    access_leader2 = UserGroupAccess(user_id=leader_user2.id, group_id=shg.id)
    db_session.add(access_leader2)

    # Initialize ledger accounts and savings for member1
    from app.domain.ledger.accounts import get_or_create_member_sub_accounts, initialize_shg_chart_of_accounts
    from app.domain.savings.service import collect_member_savings, generate_savings_dues_for_period

    await initialize_shg_chart_of_accounts(db_session, shg.id)
    await get_or_create_member_sub_accounts(db_session, shg.id, member1)
    await generate_savings_dues_for_period(db_session, shg.id, "2026-01")
    await collect_member_savings(
        db=db_session,
        shg_id=shg.id,
        member_id=member1.id,
        amount=Decimal("1000.00"),
        period="2026-01",
        posted_by=admin_user.id,
    )

    await db_session.commit()
    return {
        "shg": shg,
        "leader1": leader_user,
        "leader2": leader_user2,
        "member_user": member_user,
        "member1": member1,
        "member2": member2,
    }


# ==========================================
# 1. State Machine: Exhaustive Pair Tests
# ==========================================

ALL_STATUSES = list(LoanStatus)
ALL_STATUS_PAIRS = list(itertools.product(ALL_STATUSES, ALL_STATUSES))
INVALID_PAIRS = [
    (from_s, to_s)
    for from_s, to_s in ALL_STATUS_PAIRS
    if to_s not in VALID_TRANSITIONS.get(from_s, set())
]


@pytest.mark.parametrize("from_status,to_status", INVALID_PAIRS)
async def test_invalid_state_transitions_raise_error(
    db_session: AsyncSession,
    admin_user: User,
    from_status: LoanStatus,
    to_status: LoanStatus,
):
    """
    Every invalid state transition must strictly raise LOAN_INVALID_TRANSITION.
    """
    loan = Loan(
        shg_id=uuid.uuid4(),
        member_id=uuid.uuid4(),
        loan_number="LN-TEST",
        principal=Decimal("10000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=12,
        purpose="Livestock",
        status=from_status,
        version=1,
    )

    with pytest.raises(AppError) as exc_info:
        await LoanStateMachine.transition(
            db=db_session,
            loan=loan,
            to_status=to_status,
            actor=admin_user,
            reason="Test transition",
        )
    assert exc_info.value.code == "LOAN_INVALID_TRANSITION"


# ==========================================
# 2. Maker-Checker Enforcement Tests
# ==========================================

async def test_maker_checker_creator_cannot_approve(
    db_session: AsyncSession,
    group_with_members: dict,
):
    """A user who created/applied for the loan cannot approve it."""
    shg = group_with_members["shg"]
    leader1 = group_with_members["leader1"]
    leader2 = group_with_members["leader2"]
    member2 = group_with_members["member2"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member2.id,
        applied_by=leader1.id,
        loan_number="LN-MC-001",
        principal=Decimal("10000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        purpose="Dairy",
        status=LoanStatus.SUBMITTED,
        version=1,
    )
    db_session.add(loan)
    await db_session.commit()

    # leader1 applied -> cannot approve
    with pytest.raises(AppError) as exc:
        await LoanStateMachine.transition(
            db=db_session,
            loan=loan,
            to_status=LoanStatus.APPROVED,
            actor=leader1,
        )
    assert exc.value.code == "MAKER_CHECKER_VIOLATION"

    # leader2 did not apply -> CAN approve
    approved = await LoanStateMachine.transition(
        db=db_session,
        loan=loan,
        to_status=LoanStatus.APPROVED,
        actor=leader2,
    )
    assert approved.status == LoanStatus.APPROVED
    assert approved.approved_by == leader2.id


async def test_maker_checker_applicant_member_cannot_approve(
    db_session: AsyncSession,
    admin_user: User,
    group_with_members: dict,
):
    """A member applying for their own loan (even if they have leader privileges) cannot approve it."""
    shg = group_with_members["shg"]
    leader1 = group_with_members["leader1"]  # leader1 is linked to member1
    member1 = group_with_members["member1"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member1.id,
        applied_by=admin_user.id,  # applied by admin, but for member1
        loan_number="LN-MC-002",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        purpose="Agriculture",
        status=LoanStatus.SUBMITTED,
        version=1,
    )
    db_session.add(loan)
    await db_session.commit()

    # leader1 is the applicant member -> cannot approve
    with pytest.raises(AppError) as exc:
        await LoanStateMachine.transition(
            db=db_session,
            loan=loan,
            to_status=LoanStatus.APPROVED,
            actor=leader1,
        )
    assert exc.value.code == "MAKER_CHECKER_VIOLATION"


# ==========================================
# 3. Reason Requirement & Optimistic Locking
# ==========================================

async def test_rejection_requires_reason(
    db_session: AsyncSession,
    admin_user: User,
    group_with_members: dict,
):
    """Rejecting a loan requires a non-empty reason."""
    shg = group_with_members["shg"]
    member1 = group_with_members["member1"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member1.id,
        applied_by=admin_user.id,
        loan_number="LN-REJ-001",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        purpose="Seeds",
        status=LoanStatus.SUBMITTED,
        version=1,
    )
    db_session.add(loan)
    await db_session.commit()

    with pytest.raises(AppError) as exc:
        await LoanStateMachine.transition(
            db=db_session,
            loan=loan,
            to_status=LoanStatus.REJECTED,
            actor=admin_user,
            reason="   ",
        )
    assert exc.value.code == "REASON_REQUIRED"

    # With valid reason
    rejected = await LoanStateMachine.transition(
        db=db_session,
        loan=loan,
        to_status=LoanStatus.REJECTED,
        actor=admin_user,
        reason="Insufficient group liquidity at this time",
    )
    assert rejected.status == LoanStatus.REJECTED
    assert rejected.rejection_reason == "Insufficient group liquidity at this time"


async def test_optimistic_locking_conflict(
    db_session: AsyncSession,
    admin_user: User,
    group_with_members: dict,
):
    """Supplying a stale expected_version must raise OPTIMISTIC_LOCK_CONFLICT (409)."""
    shg = group_with_members["shg"]
    member1 = group_with_members["member1"]

    loan = Loan(
        shg_id=shg.id,
        member_id=member1.id,
        applied_by=admin_user.id,
        loan_number="LN-OPT-001",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        purpose="Seeds",
        status=LoanStatus.SUBMITTED,
        version=2,
    )
    db_session.add(loan)
    await db_session.commit()

    # Pass expected_version = 1 when version is 2
    with pytest.raises(AppError) as exc:
        await LoanStateMachine.transition(
            db=db_session,
            loan=loan,
            to_status=LoanStatus.APPROVED,
            actor=admin_user,
            expected_version=1,
        )
    assert exc.value.code == "OPTIMISTIC_LOCK_CONFLICT"
    assert exc.value.status_code == 409


# ==========================================
# 4. Eligibility Check Tests
# ==========================================

async def test_eligibility_blocker_on_exited_member(
    db_session: AsyncSession,
    group_with_members: dict,
):
    """An EXITED member fails the active member check with a BLOCKER."""
    shg = group_with_members["shg"]
    member2 = group_with_members["member2"]
    member2.status = MemberStatus.EXITED
    await db_session.commit()

    result = await evaluate_loan_eligibility(
        db=db_session,
        shg_id=shg.id,
        member_id=member2.id,
        principal=Decimal("10000.00"),
        tenure_months=12,
    )
    assert not result.is_eligible
    active_check = next(c for c in result.checks if c.code == "MEMBER_ACTIVE")
    assert not active_check.passed
    assert active_check.severity == "BLOCKER"


# ==========================================
# 5. Full API Endpoints Flow
# ==========================================

async def test_loan_api_lifecycle(
    client: AsyncClient,
    admin_user: User,
    group_with_members: dict,
):
    """
    Verify full loan lifecycle via HTTP API:
    1. Preview schedule
    2. Create draft loan
    3. Submit loan
    4. Verify maker-checker on GET
    5. Approve loan
    6. Verify status history audit
    """
    shg = group_with_members["shg"]
    member1 = group_with_members["member1"]
    leader2 = group_with_members["leader2"]

    from app.core.security import create_access_token

    leader2_token = create_access_token(subject=str(leader2.id), role=leader2.role.value)
    headers = {"Authorization": f"Bearer {leader2_token}"}

    # 1. Preview schedule
    preview_res = await client.post(
        "/api/v1/loans/preview-schedule",
        headers=headers,
        json={
            "shg_id": str(shg.id),
            "member_id": str(member1.id),
            "principal": "50000.00",
            "annual_rate": "12.00",
            "interest_type": "REDUCING",
            "tenure_months": 12,
            "first_due_date": "2026-04-01",
        },
    )
    assert preview_res.status_code == 200
    preview_data = preview_res.json()
    assert preview_data["monthly_installment"] == "4442.44"
    assert len(preview_data["installments"]) == 12

    # 2. Create draft loan as leader2
    create_res = await client.post(
        "/api/v1/loans",
        headers=headers,
        json={
            "shg_id": str(shg.id),
            "member_id": str(member1.id),
            "principal": "2000.00",
            "interest_rate": "12.00",
            "interest_type": "REDUCING",
            "tenure_months": 6,
            "purpose": "Fertilizer purchase",
            "first_due_date": "2026-05-01",
        },
    )
    assert create_res.status_code == 201, create_res.text
    loan_data = create_res.json()
    loan_id = loan_data["id"]
    assert loan_data["status"] == "DRAFT"
    assert loan_data["version"] == 1

    # 3. Submit loan
    submit_res = await client.post(f"/api/v1/loans/{loan_id}/submit", headers=headers)
    assert submit_res.status_code == 200
    assert submit_res.json()["status"] == "SUBMITTED"
    assert submit_res.json()["version"] == 2

    # 4. Check Maker-Checker via GET loan
    # leader2 created it -> cannot approve
    get_res_leader2 = await client.get(f"/api/v1/loans/{loan_id}", headers=headers)
    assert get_res_leader2.status_code == 200
    assert get_res_leader2.json()["can_approve"] is False
    assert "maker-checker" in get_res_leader2.json()["maker_checker_note"].lower()
    assert "cannot approve" in get_res_leader2.json()["maker_checker_note"].lower()

    # Admin CAN approve
    admin_token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    get_res_admin = await client.get(f"/api/v1/loans/{loan_id}", headers=admin_headers)
    assert get_res_admin.status_code == 200
    assert get_res_admin.json()["can_approve"] is True

    # 5. Leader2 attempting to approve fails
    approve_fail = await client.post(
        f"/api/v1/loans/{loan_id}/approve",
        headers=headers,
        json={"version": 2},
    )
    assert approve_fail.status_code in [400, 403]
    assert approve_fail.json()["code"] == "MAKER_CHECKER_VIOLATION"

    # Admin approves
    approve_res = await client.post(
        f"/api/v1/loans/{loan_id}/approve",
        headers=admin_headers,
        json={"version": 2},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"
    assert approve_res.json()["version"] == 3

    # 6. Check history
    hist_res = await client.get(f"/api/v1/loans/{loan_id}/history", headers=admin_headers)
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) == 2  # DRAFT -> SUBMITTED, SUBMITTED -> APPROVED
    assert history[0]["from_status"] == "DRAFT"
    assert history[0]["to_status"] == "SUBMITTED"
    assert history[1]["from_status"] == "SUBMITTED"
    assert history[1]["to_status"] == "APPROVED"
