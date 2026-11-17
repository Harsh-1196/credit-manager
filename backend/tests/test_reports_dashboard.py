import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.models.auth import User, UserGroupAccess, UserRole
from app.db.models.ledger import Account, AccountType, JournalEntry, JournalLine, JournalSourceType
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.meetings import Meeting, MeetingStatus
from app.db.models.savings import SavingsDue, SavingsDueStatus
from app.db.models.shg import SHG, GroupSettings, InterestType, Member, MemberStatus
from app.domain.ledger.accounts import initialize_shg_chart_of_accounts
from app.domain.outbox.service import get_or_create_dashboard_read_model


@pytest.fixture
async def setup_report_data(db_session: AsyncSession):
    # 1. Create SHG
    shg = SHG(
        id=uuid.uuid4(),
        name="Udaan Mahila Mandal",
        village="Rampur",
        district="Varanasi",
        formation_date=date(2025, 1, 1),
        meeting_day="MONDAY",
        meeting_frequency="MONTHLY",
        status="ACTIVE",
    )
    db_session.add(shg)
    await db_session.flush()

    settings = GroupSettings(
        id=uuid.uuid4(),
        shg_id=shg.id,
        monthly_saving_amount=Decimal("500.00"),
        late_fine_per_day=Decimal("5.00"),
        fine_grace_days=5,
        default_interest_rate=Decimal("12.000"),
        interest_type=InterestType.REDUCING,
    )
    db_session.add(settings)

    # Chart of accounts
    await initialize_shg_chart_of_accounts(db_session, shg.id)

    # 2. Users: Admin, Leader, Member
    admin = User(
        id=uuid.uuid4(),
        email="admin_rep@shg.org",
        password_hash="pw",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)

    leader = User(
        id=uuid.uuid4(),
        email="leader_rep@shg.org",
        password_hash="pw",
        role=UserRole.GROUP_LEADER,
        is_active=True,
    )
    db_session.add(leader)
    await db_session.flush()

    uga = UserGroupAccess(user_id=leader.id, group_id=shg.id)
    db_session.add(uga)

    member_user = User(
        id=uuid.uuid4(),
        email="member_rep@shg.org",
        password_hash="pw",
        role=UserRole.MEMBER,
        is_active=True,
    )
    db_session.add(member_user)
    await db_session.flush()

    member = Member(
        id=uuid.uuid4(),
        shg_id=shg.id,
        user_id=member_user.id,
        full_name="Radha Devi",
        phone="9876543210",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(member)

    member_user2 = User(
        id=uuid.uuid4(),
        email="member2_rep@shg.org",
        password_hash="pw",
        role=UserRole.MEMBER,
        is_active=True,
    )
    db_session.add(member_user2)
    await db_session.flush()

    member2 = Member(
        id=uuid.uuid4(),
        shg_id=shg.id,
        user_id=member_user2.id,
        full_name="Meena Kumari",
        phone="9876543211",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(member2)
    await db_session.flush()

    # Create savings sub-account for member
    mem_sub_code = f"2000-{str(member.id)[:8]}"
    savings_acc = Account(
        id=uuid.uuid4(),
        shg_id=shg.id,
        code=mem_sub_code,
        name=f"Savings - {member.full_name}",
        type=AccountType.LIABILITY,
        member_id=member.id,
    )
    db_session.add(savings_acc)

    # Initial Corpus Entry: Cash 50,000, Capital 50,000
    entry1 = JournalEntry(
        id=uuid.uuid4(),
        shg_id=shg.id,
        entry_date=date(2026, 1, 15),
        description="Initial group corpus",
        source_type=JournalSourceType.SAVINGS,
        posted_by=admin.id,
        created_at=datetime.now(UTC),
    )
    db_session.add(entry1)
    await db_session.flush()

    cash_acc = (
        await db_session.execute(
            select(Account).where(Account.shg_id == shg.id, Account.code == "1000")
        )
    ).scalar_one()
    capital_acc = (
        await db_session.execute(
            select(Account).where(Account.shg_id == shg.id, Account.code == "3000")
        )
    ).scalar_one()

    l1 = JournalLine(entry_id=entry1.id, account_id=cash_acc.id, debit=Decimal("50000.00"), credit=Decimal("0.00"))
    l2 = JournalLine(entry_id=entry1.id, account_id=capital_acc.id, debit=Decimal("0.00"), credit=Decimal("50000.00"))
    db_session.add_all([l1, l2])

    # Member Savings Deposit: Cash 2,000, Member Savings 2,000
    entry2 = JournalEntry(
        id=uuid.uuid4(),
        shg_id=shg.id,
        entry_date=date(2026, 2, 1),
        description=f"Savings deposit - {member.full_name}",
        source_type=JournalSourceType.SAVINGS,
        posted_by=admin.id,
        created_at=datetime.now(UTC),
    )
    db_session.add(entry2)
    await db_session.flush()

    l3 = JournalLine(entry_id=entry2.id, account_id=cash_acc.id, debit=Decimal("2000.00"), credit=Decimal("0.00"))
    l4 = JournalLine(entry_id=entry2.id, account_id=savings_acc.id, debit=Decimal("0.00"), credit=Decimal("2000.00"))
    db_session.add_all([l3, l4])

    # Loan Disbursed
    loan_acc = (
        await db_session.execute(
            select(Account).where(Account.shg_id == shg.id, Account.code == "1100")
        )
    ).scalar_one()

    loan = Loan(
        id=uuid.uuid4(),
        shg_id=shg.id,
        member_id=member.id,
        loan_number="LN-2026-001",
        purpose="Dairy farming",
        principal=Decimal("10000.00"),
        interest_rate=Decimal("12.000"),
        interest_type=InterestType.REDUCING,
        tenure_months=10,
        status=LoanStatus.ACTIVE,
        applied_by=leader.id,
        applied_at=datetime.now(UTC),
        disbursed_at=datetime(2026, 2, 5, 10, 0, tzinfo=UTC),
    )
    db_session.add(loan)
    await db_session.flush()

    # Loan schedule item (overdue)
    sch1 = LoanSchedule(
        id=uuid.uuid4(),
        loan_id=loan.id,
        installment_no=1,
        due_date=date(2026, 2, 28),
        principal_due=Decimal("1000.00"),
        interest_due=Decimal("100.00"),
        total_due=Decimal("1100.00"),
        penalty_due=Decimal("0.00"),
        principal_paid=Decimal("0.00"),
        interest_paid=Decimal("0.00"),
        penalty_paid=Decimal("0.00"),
        status=LoanScheduleStatus.OVERDUE,
    )
    db_session.add(sch1)

    # Disburse Journal: Loan Rec 10,000 / Cash 10,000
    entry3 = JournalEntry(
        id=uuid.uuid4(),
        shg_id=shg.id,
        entry_date=date(2026, 2, 5),
        description=f"Loan disbursal {loan.loan_number}",
        source_type=JournalSourceType.DISBURSAL,
        posted_by=admin.id,
        created_at=datetime.now(UTC),
    )
    db_session.add(entry3)
    await db_session.flush()

    l5 = JournalLine(entry_id=entry3.id, account_id=loan_acc.id, debit=Decimal("10000.00"), credit=Decimal("0.00"))
    l6 = JournalLine(entry_id=entry3.id, account_id=cash_acc.id, debit=Decimal("0.00"), credit=Decimal("10000.00"))
    db_session.add_all([l5, l6])

    # Pending Savings Due
    sdue = SavingsDue(
        id=uuid.uuid4(),
        shg_id=shg.id,
        member_id=member2.id,
        period="2026-03",
        amount_due=Decimal("500.00"),
        amount_paid=Decimal("0.00"),
        status=SavingsDueStatus.PENDING,
    )
    db_session.add(sdue)

    # Meeting
    meeting = Meeting(
        id=uuid.uuid4(),
        shg_id=shg.id,
        meeting_date=date(2026, 3, 10),
        status=MeetingStatus.SCHEDULED,
        agenda="Monthly collections and savings",
    )
    db_session.add(meeting)

    # Update Read Model
    rm = await get_or_create_dashboard_read_model(db_session, shg.id)
    rm.group_cash_balance = Decimal("42000.00")
    rm.total_savings = Decimal("2000.00")
    rm.total_principal_outstanding = Decimal("10000.00")
    rm.total_interest_collected = Decimal("0.00")
    rm.active_loans_count = 1

    await db_session.commit()

    return {
        "shg": shg,
        "admin": admin,
        "leader": leader,
        "member_user": member_user,
        "member": member,
        "member_user2": member_user2,
        "meeting": meeting,
    }


@pytest.mark.asyncio
async def test_dashboard_role_aware_admin_and_member(client: AsyncClient, setup_report_data):
    data = setup_report_data
    shg = data["shg"]
    admin = data["admin"]
    member_user = data["member_user"]

    admin_token = create_access_token(admin.id, admin.role.value)
    member_token = create_access_token(member_user.id, member_user.role.value)

    # 1. Admin gets group dashboard
    res_admin = await client.get(
        f"/api/v1/dashboard?shg_id={shg.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 200
    body_admin = res_admin.json()
    assert body_admin["role"] == "ADMIN"
    assert body_admin["group_dashboard"] is not None
    assert body_admin["member_dashboard"] is None

    figs = body_admin["group_dashboard"]["figures"]
    assert Decimal(str(figs["total_corpus"])) == Decimal("42000.00")
    assert Decimal(str(figs["total_savings"])) == Decimal("2000.00")
    assert Decimal(str(figs["outstanding_principal"])) == Decimal("10000.00")
    assert len(body_admin["group_dashboard"]["savings_trend"]) > 0
    assert len(body_admin["group_dashboard"]["aging_buckets"]) == 5

    # 2. Member gets member statement view
    res_mem = await client.get(
        "/api/v1/dashboard",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res_mem.status_code == 200
    body_mem = res_mem.json()
    assert body_mem["role"] == "MEMBER"
    assert body_mem["member_dashboard"] is not None
    assert body_mem["group_dashboard"] is None

    mem_summary = body_mem["member_dashboard"]["member"]
    assert mem_summary["name"] == "Radha Devi"
    assert Decimal(str(mem_summary["total_savings_balance"])) == Decimal("2000.00")
    assert len(body_mem["member_dashboard"]["passbook_entries"]) == 1
    assert len(body_mem["member_dashboard"]["active_loans"]) == 1


@pytest.mark.asyncio
async def test_group_dashboard_report_json_and_csv(client: AsyncClient, setup_report_data):
    data = setup_report_data
    shg = data["shg"]
    admin = data["admin"]
    member_user = data["member_user"]

    admin_token = create_access_token(admin.id, admin.role.value)
    member_token = create_access_token(member_user.id, member_user.role.value)

    # JSON format
    res_json = await client.get(
        f"/api/v1/reports/group-dashboard?shg_id={shg.id}&format=json",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_json.status_code == 200
    assert res_json.headers["content-type"] == "application/json"
    body = res_json.json()
    assert body["shg_name"] == "Udaan Mahila Mandal"
    assert len(body["collections_due"]) > 0

    # CSV format
    res_csv = await client.get(
        f"/api/v1/reports/group-dashboard?shg_id={shg.id}&format=csv",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "Total Corpus,42000.00" in res_csv.text
    assert "Total Savings,2000.00" in res_csv.text

    # Member unauthorized for group dashboard
    res_unauth = await client.get(
        f"/api/v1/reports/group-dashboard?shg_id={shg.id}&format=json",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res_unauth.status_code == 403


@pytest.mark.asyncio
async def test_member_statement_report_permissions_and_csv(client: AsyncClient, setup_report_data):
    data = setup_report_data
    admin = data["admin"]
    member_user = data["member_user"]
    member = data["member"]
    member_user2 = data["member_user2"]

    admin_token = create_access_token(admin.id, admin.role.value)
    mem1_token = create_access_token(member_user.id, member_user.role.value)
    mem2_token = create_access_token(member_user2.id, member_user2.role.value)

    # 1. Member views own statement (allowed)
    res_own = await client.get(
        f"/api/v1/reports/member-statement?member_id={member.id}&format=json",
        headers={"Authorization": f"Bearer {mem1_token}"},
    )
    assert res_own.status_code == 200
    assert res_own.json()["member"]["name"] == "Radha Devi"

    # 2. Member views another member's statement (403 forbidden)
    res_other = await client.get(
        f"/api/v1/reports/member-statement?member_id={member.id}&format=json",
        headers={"Authorization": f"Bearer {mem2_token}"},
    )
    assert res_other.status_code == 403

    # 3. Admin views member statement (allowed) and gets CSV
    res_admin_csv = await client.get(
        f"/api/v1/reports/member-statement?member_id={member.id}&format=csv",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin_csv.status_code == 200
    assert "text/csv" in res_admin_csv.headers["content-type"]
    assert "Member Statement,Radha Devi" in res_admin_csv.text
    assert "Passbook Ledger Entries" in res_admin_csv.text


@pytest.mark.asyncio
async def test_group_ledger_report_and_trial_balance(client: AsyncClient, setup_report_data):
    data = setup_report_data
    shg = data["shg"]
    admin = data["admin"]

    admin_token = create_access_token(admin.id, admin.role.value)

    res = await client.get(
        f"/api/v1/reports/group-ledger?shg_id={shg.id}&format=json",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["trial_balance"]) > 0
    assert len(body["journal_entries"]) == 3

    # Assert trial balance balances: total debits == total credits
    tot_debits = sum(Decimal(tb["debit_balance"]) for tb in body["trial_balance"])
    tot_credits = sum(Decimal(tb["credit_balance"]) for tb in body["trial_balance"])
    assert tot_debits == tot_credits
    assert tot_debits == Decimal("62000.00")  # 50,000 + 2,000 + 10,000


@pytest.mark.asyncio
async def test_loan_portfolio_report_and_csv(client: AsyncClient, setup_report_data):
    data = setup_report_data
    shg = data["shg"]
    admin = data["admin"]

    admin_token = create_access_token(admin.id, admin.role.value)

    res = await client.get(
        f"/api/v1/reports/loan-portfolio?shg_id={shg.id}&format=csv",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "Loan Portfolio Report,Udaan Mahila Mandal" in res.text
    assert "active_loans_count,1" in res.text
    assert "total_outstanding_principal,10000.00" in res.text
    assert "LN-2026-001" in res.text
