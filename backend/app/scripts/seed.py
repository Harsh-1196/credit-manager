from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import quantize_money
from app.core.security import hash_password
from app.db.models.auth import User, UserGroupAccess, UserRole
from app.db.models.ledger import JournalSourceType
from app.db.models.loans import Loan, LoanStatus
from app.db.models.meetings import AttendanceStatus, Meeting, MeetingStatus
from app.db.models.shg import (
    SHG,
    GroupSettings,
    InterestType,
    Member,
    MemberRole,
    MemberStatus,
    OfficeBearerRole,
    SHGStatus,
)
from app.db.session import AsyncSessionLocal
from app.domain.ledger.accounts import (
    get_account_by_code,
    get_or_create_member_sub_accounts,
    initialize_shg_chart_of_accounts,
)
from app.domain.ledger.posting import PostingLineDTO, post_journal_entry, reverse_journal_entry
from app.domain.loans.state_machine import LoanStateMachine
from app.domain.savings.service import generate_savings_dues_for_period
from app.schemas.meetings import MeetingBatchCollectionItem, MeetingBatchCollectionsRequest
from app.services.loans import disburse_loan, repay_loan
from app.services.meetings import record_meeting_batch_collections


async def _create_seed_loan(
    db: AsyncSession,
    shg_id: uuid.UUID,
    member_id: uuid.UUID,
    loan_number: str,
    principal: Decimal,
    interest_rate: Decimal,
    interest_type: InterestType,
    tenure_months: int,
    purpose: str,
    applied_by_id: uuid.UUID,
    first_due_date: date,
) -> Loan:
    proc_fee = quantize_money(principal * Decimal("0.01"))
    loan = Loan(
        shg_id=shg_id,
        member_id=member_id,
        loan_number=loan_number,
        purpose=purpose,
        principal=quantize_money(principal),
        interest_rate=interest_rate,
        interest_type=interest_type,
        tenure_months=tenure_months,
        processing_fee=proc_fee,
        status=LoanStatus.DRAFT,
        applied_by=applied_by_id,
        first_due_date=first_due_date,
        version=1,
    )
    db.add(loan)
    await db.flush()

    return loan


async def seed_data() -> None:
    async with AsyncSessionLocal() as db:
        print("=" * 80)
        print("SHG Credit Manager: Database Seeding (SPEC Section 16)")
        print("=" * 80)

        # Check existing admin
        admin_check = await db.scalar(select(User.id).where(User.email == "admin@shg.org"))
        if admin_check:
            print("[INFO] Seed data already present in database. Skipping duplicate seed.")
            print_demo_logins()
            return

        # -------------------------------------------------------------------------
        # 1. System Users (Admin & Auditor)
        # -------------------------------------------------------------------------
        print("1. Creating System Users (ADMIN, AUDITOR)...")
        admin_user = User(
            email="admin@shg.org",
            phone="9876543210",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        auditor_user = User(
            email="auditor@shg.org",
            phone="9876543211",
            password_hash=hash_password("AuditorPass123!"),
            role=UserRole.AUDITOR,
            is_active=True,
        )
        db.add_all([admin_user, auditor_user])
        await db.flush()

        # -------------------------------------------------------------------------
        # 2. SHG 1: Pragati Mahila Mandal (Village: Rampur)
        # -------------------------------------------------------------------------
        print("2. Seeding SHG 1: Pragati Mahila Mandal (Rampur)...")
        leader1_user = User(
            email="leader1@shg.org",
            phone="9876543220",
            password_hash=hash_password("LeaderPass123!"),
            role=UserRole.GROUP_LEADER,
            is_active=True,
        )
        db.add(leader1_user)
        await db.flush()

        shg1 = SHG(
            name="Pragati Mahila Mandal",
            village="Rampur",
            ward="Ward 3",
            district="Varanasi",
            formation_date=date(2024, 6, 1),
            meeting_day="1st Monday",
            meeting_frequency="MONTHLY",
            bank_account_label="SBI A/c **4589",
            status=SHGStatus.ACTIVE,
        )
        db.add(shg1)
        await db.flush()

        settings1 = GroupSettings(
            shg_id=shg1.id,
            monthly_saving_amount=Decimal("500.00"),
            late_fine_per_day=Decimal("5.00"),
            fine_grace_days=5,
            default_interest_rate=Decimal("12.000"),
            interest_type=InterestType.REDUCING,
            max_loan_multiple=Decimal("8.00"),
            min_tenure_months=1,
            max_tenure_months=24,
            processing_fee_percent=Decimal("1.000"),
            penalty_interest_rate=Decimal("2.000"),
        )
        db.add(settings1)

        db.add_all([
            UserGroupAccess(user_id=leader1_user.id, group_id=shg1.id, access_level="LEADER"),
            UserGroupAccess(user_id=auditor_user.id, group_id=shg1.id, access_level="AUDITOR"),
        ])
        await db.flush()

        await initialize_shg_chart_of_accounts(db, shg1.id)

        # 12 Members for SHG 1 with realistic non-round demographics
        shg1_member_names = [
            ("Sunita Devi", "9876543221", "East Tola, Rampur", OfficeBearerRole.PRESIDENT),
            ("Radha Sharma", "9876543222", "Main Bazar, Rampur", OfficeBearerRole.SECRETARY),
            ("Meera Patel", "9876543223", "Gali No 4, Rampur", OfficeBearerRole.TREASURER),
            ("Geeta Verma", "9876543224", "Near Pond, Rampur", OfficeBearerRole.MEMBER),
            ("Savitri Bai", "9876543225", "Harijan Basti, Rampur", OfficeBearerRole.MEMBER),
            ("Kaushalya Devi", "9876543226", "School Road, Rampur", OfficeBearerRole.MEMBER),
            ("Rekha Yadav", "9876543227", "Yadav Tola, Rampur", OfficeBearerRole.MEMBER),
            ("Pushpa Devi", "9876543228", "West Tola, Rampur", OfficeBearerRole.MEMBER),
            ("Shanti Devi", "9876543229", "Chaupal, Rampur", OfficeBearerRole.MEMBER),
            ("Usha Mishra", "9876543230", "Brahmin Basti, Rampur", OfficeBearerRole.MEMBER),
            ("Sarita Bind", "9876543231", "River Bank, Rampur", OfficeBearerRole.MEMBER),
            ("Manju Gupta", "9876543232", "Post Office Lane, Rampur", OfficeBearerRole.MEMBER),
        ]

        shg1_members: list[Member] = []
        for idx, (m_name, m_phone, m_addr, m_role) in enumerate(shg1_member_names):
            m_user = None
            if idx == 0:
                # Sunita Devi linked to demo member user
                m_user = User(
                    email="member@shg.org",
                    phone=m_phone,
                    password_hash=hash_password("MemberPass123!"),
                    role=UserRole.MEMBER,
                    is_active=True,
                )
                db.add(m_user)
                await db.flush()
                db.add(UserGroupAccess(user_id=m_user.id, group_id=shg1.id, access_level="MEMBER"))

            mem = Member(
                shg_id=shg1.id,
                user_id=m_user.id if m_user else None,
                full_name=m_name,
                phone=m_phone,
                address=m_addr,
                id_proof_type="Aadhaar",
                id_proof_last4=f"{1000 + idx * 77}",
                date_of_birth=date(1985 + (idx % 12), ((idx * 3) % 12) + 1, 15),
                joined_on=date(2024, 6, 1),
                status=MemberStatus.ACTIVE,
            )
            db.add(mem)
            await db.flush()
            db.add(MemberRole(member_id=mem.id, role=m_role, from_date=date(2024, 6, 1)))
            await get_or_create_member_sub_accounts(db, shg1.id, mem)
            shg1_members.append(mem)

        # -------------------------------------------------------------------------
        # 3. SHG 2: Udaan Swayam Sahayata Samuh (Village: Chandpur)
        # -------------------------------------------------------------------------
        print("3. Seeding SHG 2: Udaan Swayam Sahayata Samuh (Chandpur)...")
        leader2_user = User(
            email="leader2@shg.org",
            phone="9876543240",
            password_hash=hash_password("LeaderPass123!"),
            role=UserRole.GROUP_LEADER,
            is_active=True,
        )
        db.add(leader2_user)
        await db.flush()

        shg2 = SHG(
            name="Udaan Swayam Sahayata Samuh",
            village="Chandpur",
            ward="Ward 7",
            district="Varanasi",
            formation_date=date(2024, 7, 15),
            meeting_day="2nd Saturday",
            meeting_frequency="MONTHLY",
            bank_account_label="Bank of Baroda A/c **8832",
            status=SHGStatus.ACTIVE,
        )
        db.add(shg2)
        await db.flush()

        settings2 = GroupSettings(
            shg_id=shg2.id,
            monthly_saving_amount=Decimal("400.00"),
            late_fine_per_day=Decimal("5.00"),
            fine_grace_days=5,
            default_interest_rate=Decimal("12.000"),
            interest_type=InterestType.REDUCING,
            max_loan_multiple=Decimal("8.00"),
            min_tenure_months=1,
            max_tenure_months=24,
            processing_fee_percent=Decimal("1.000"),
            penalty_interest_rate=Decimal("2.000"),
        )
        db.add(settings2)

        db.add_all([
            UserGroupAccess(user_id=leader2_user.id, group_id=shg2.id, access_level="LEADER"),
            UserGroupAccess(user_id=auditor_user.id, group_id=shg2.id, access_level="AUDITOR"),
        ])
        await db.flush()

        await initialize_shg_chart_of_accounts(db, shg2.id)

        shg2_member_names = [
            ("Kamla Devi", "9876543241", "North Chandpur", OfficeBearerRole.PRESIDENT),
            ("Nirmala Kushwaha", "9876543242", "Station Road, Chandpur", OfficeBearerRole.SECRETARY),
            ("Basanti Devi", "9876543243", "Panchayat Bhawan, Chandpur", OfficeBearerRole.TREASURER),
            ("Champa Devi", "9876543244", "Bazar, Chandpur", OfficeBearerRole.MEMBER),
            ("Tara Bai", "9876543245", "Kushwaha Basti, Chandpur", OfficeBearerRole.MEMBER),
            ("Kanti Devi", "9876543246", "Near Canal, Chandpur", OfficeBearerRole.MEMBER),
            ("Lalita Maurya", "9876543247", "Maurya Tola, Chandpur", OfficeBearerRole.MEMBER),
            ("Munni Devi", "9876543248", "South Chandpur", OfficeBearerRole.MEMBER),
            ("Damyanti Devi", "9876543249", "Mandir Marg, Chandpur", OfficeBearerRole.MEMBER),
            ("Anandi Bai", "9876543250", "Gali No 1, Chandpur", OfficeBearerRole.MEMBER),
            ("Kiran Rawat", "9876543251", "Rawat Tola, Chandpur", OfficeBearerRole.MEMBER),
            ("Sudha Chauhan", "9876543252", "High School Road, Chandpur", OfficeBearerRole.MEMBER),
        ]

        shg2_members: list[Member] = []
        for idx, (m_name, m_phone, m_addr, m_role) in enumerate(shg2_member_names):
            mem = Member(
                shg_id=shg2.id,
                full_name=m_name,
                phone=m_phone,
                address=m_addr,
                id_proof_type="Aadhaar",
                id_proof_last4=f"{2000 + idx * 83}",
                date_of_birth=date(1987 + (idx % 10), ((idx * 4) % 12) + 1, 20),
                joined_on=date(2024, 7, 15),
                status=MemberStatus.ACTIVE,
            )
            db.add(mem)
            await db.flush()
            db.add(MemberRole(member_id=mem.id, role=m_role, from_date=date(2024, 7, 15)))
            await get_or_create_member_sub_accounts(db, shg2.id, mem)
            shg2_members.append(mem)

        # -------------------------------------------------------------------------
        # 4. Six Months of Historical Meetings & Collections (SPEC Section 16)
        # -------------------------------------------------------------------------
        print("4. Seeding 6 months of historical meetings and double-entry collections...")
        today = date.today()
        # Compute dates for 6 monthly meetings (Months -5 down to Month 0)
        meeting_dates_shg1 = []
        meeting_dates_shg2 = []
        for i in range(5, -1, -1):
            m_date = today.replace(day=5) - timedelta(days=i * 30)
            meeting_dates_shg1.append(m_date)
            m_date2 = today.replace(day=12) - timedelta(days=i * 30)
            meeting_dates_shg2.append(m_date2)

        # Process SHG 1 meetings and collections
        for m_idx, m_date in enumerate(meeting_dates_shg1):
            period = m_date.strftime("%Y-%m")
            meeting = Meeting(
                shg_id=shg1.id,
                meeting_date=m_date,
                status=MeetingStatus.HELD,
            )
            db.add(meeting)
            await db.flush()

            # Generate monthly savings dues
            await generate_savings_dues_for_period(db, shg1.id, period)

            # Build collection payload for members
            collections_list = []
            for mem_idx, mem in enumerate(shg1_members):
                # Realistic attendance: mostly PRESENT, occasionally ABSENT
                is_absent = (mem_idx == 4 and m_idx == 2) or (mem_idx == 7 and m_idx == 4)
                att_status = AttendanceStatus.ABSENT if is_absent else AttendanceStatus.PRESENT

                # Savings: ₹500 if present, 0 if absent
                sav_amt = Decimal("0.00") if is_absent else Decimal("500.00")
                # Fines: occasional fine for late arrival or absence
                fine_amt = Decimal("15.00") if (mem_idx == 3 and m_idx == 1) else Decimal("0.00")

                collections_list.append(
                    MeetingBatchCollectionItem(
                        member_id=mem.id,
                        attendance_status=att_status,
                        savings_amount=sav_amt,
                        loan_repayment_amount=Decimal("0.00"),
                        fine_amount=fine_amt,
                    )
                )

            batch_req = MeetingBatchCollectionsRequest(
                collections=collections_list,
                period=period,
                idempotency_key=f"seed-shg1-m{m_idx}-{uuid.uuid4().hex[:8]}",
            )
            await record_meeting_batch_collections(
                db=db,
                meeting_id=meeting.id,
                shg_id=shg1.id,
                payload=batch_req,
                current_user=leader1_user,
            )

        # Process SHG 2 meetings and collections
        for m_idx, m_date in enumerate(meeting_dates_shg2):
            period = m_date.strftime("%Y-%m")
            meeting = Meeting(
                shg_id=shg2.id,
                meeting_date=m_date,
                status=MeetingStatus.HELD,
            )
            db.add(meeting)
            await db.flush()

            await generate_savings_dues_for_period(db, shg2.id, period)

            collections_list = []
            for mem_idx, mem in enumerate(shg2_members):
                is_absent = (mem_idx == 5 and m_idx == 1)
                att_status = AttendanceStatus.ABSENT if is_absent else AttendanceStatus.PRESENT
                sav_amt = Decimal("0.00") if is_absent else Decimal("400.00")
                fine_amt = Decimal("25.00") if (mem_idx == 2 and m_idx == 3) else Decimal("0.00")

                collections_list.append(
                    MeetingBatchCollectionItem(
                        member_id=mem.id,
                        attendance_status=att_status,
                        savings_amount=sav_amt,
                        loan_repayment_amount=Decimal("0.00"),
                        fine_amount=fine_amt,
                    )
                )

            batch_req = MeetingBatchCollectionsRequest(
                collections=collections_list,
                period=period,
                idempotency_key=f"seed-shg2-m{m_idx}-{uuid.uuid4().hex[:8]}",
            )
            await record_meeting_batch_collections(
                db=db,
                meeting_id=meeting.id,
                shg_id=shg2.id,
                payload=batch_req,
                current_user=leader2_user,
            )

        # -------------------------------------------------------------------------
        # 5. Loans in Every State (ACTIVE, CLOSED, OVERDUE, REJECTED, SUBMITTED)
        # -------------------------------------------------------------------------
        print("5. Seeding loans across all lifecycle states per SPEC section 16...")

        # Loan 1: ACTIVE (Sunita Devi, SHG 1) - ₹18,450.00 for Buffalo Dairy
        print("  - Creating and disbursing Loan 1 (ACTIVE)...")
        l1 = await _create_seed_loan(
            db, shg1.id, shg1_members[0].id, "LN-0001",
            Decimal("18450.00"), Decimal("12.000"), InterestType.REDUCING, 12,
            "Dairy buffalo purchase & fodder supplies", leader1_user.id, meeting_dates_shg1[-2],
        )
        await LoanStateMachine.transition(db, l1, LoanStatus.SUBMITTED, actor=leader1_user, reason="Submitted for review")
        await LoanStateMachine.transition(db, l1, LoanStatus.APPROVED, actor=admin_user, reason="Approved by general body")
        await disburse_loan(
            db=db,
            loan_id=l1.id,
            shg_id=shg1.id,
            current_user=admin_user,
            first_due_date=meeting_dates_shg1[-2],
            expected_version=l1.version,
            idempotency_key=f"seed-disb-l1-{uuid.uuid4().hex[:8]}",
        )

        # Loan 2: CLOSED (Meera Patel, SHG 1) - ₹12,750.00 (Fully repaid with interest)
        print("  - Creating, disbursing, and repaying Loan 2 (CLOSED)...")
        l2 = await _create_seed_loan(
            db, shg1.id, shg1_members[2].id, "LN-0002",
            Decimal("12750.00"), Decimal("12.000"), InterestType.REDUCING, 6,
            "Small Kirana grocery store expansion", leader1_user.id, meeting_dates_shg1[0],
        )
        await LoanStateMachine.transition(db, l2, LoanStatus.SUBMITTED, actor=leader1_user, reason="Submitted for review")
        await LoanStateMachine.transition(db, l2, LoanStatus.APPROVED, actor=admin_user, reason="Approved unanimously")
        await disburse_loan(
            db=db,
            loan_id=l2.id,
            shg_id=shg1.id,
            current_user=admin_user,
            first_due_date=meeting_dates_shg1[0],
            expected_version=l2.version,
            idempotency_key=f"seed-disb-l2-{uuid.uuid4().hex[:8]}",
        )
        # Fully close Loan 2 by paying total balance
        l2_payoff = sum(
            ((s.total_due - s.principal_paid - s.interest_paid) for s in l2.schedule),
            Decimal("0.00"),
        )
        await repay_loan(
            db=db,
            loan_id=l2.id,
            shg_id=shg1.id,
            current_user=leader1_user,
            amount=l2_payoff,
            payment_date=today,
            idempotency_key=f"seed-close-l2-{uuid.uuid4().hex[:8]}",
        )

        # Loan 3: OVERDUE (Geeta Verma, SHG 1) - ₹14,500.00
        print("  - Creating and marking Loan 3 (OVERDUE)...")
        l3 = await _create_seed_loan(
            db, shg1.id, shg1_members[3].id, "LN-0003",
            Decimal("14500.00"), Decimal("12.000"), InterestType.REDUCING, 12,
            "Sewing machines and textile tailoring inventory", leader1_user.id, today - timedelta(days=65),
        )
        await LoanStateMachine.transition(db, l3, LoanStatus.SUBMITTED, actor=leader1_user, reason="Submitted")
        await LoanStateMachine.transition(db, l3, LoanStatus.APPROVED, actor=admin_user, reason="Approved")
        await disburse_loan(
            db=db,
            loan_id=l3.id,
            shg_id=shg1.id,
            current_user=admin_user,
            first_due_date=today - timedelta(days=65),
            expected_version=l3.version,
            idempotency_key=f"seed-disb-l3-{uuid.uuid4().hex[:8]}",
        )
        # Transition to OVERDUE per state machine
        await LoanStateMachine.transition(
            db, l3, LoanStatus.OVERDUE, actor=admin_user, reason="Installment past due by 60 days"
        )

        # Loan 4: REJECTED (Rekha Yadav, SHG 1) - ₹16,000.00
        print("  - Creating and rejecting Loan 4 (REJECTED)...")
        l4 = await _create_seed_loan(
            db, shg1.id, shg1_members[6].id, "LN-0004",
            Decimal("16000.00"), Decimal("12.000"), InterestType.REDUCING, 12,
            "Purchase of mini transport auto-rickshaw", leader1_user.id, today + timedelta(days=30),
        )
        await LoanStateMachine.transition(db, l4, LoanStatus.SUBMITTED, actor=leader1_user, reason="Submitted")
        l4.rejection_reason = "Incomplete guarantor documentation and past delinquency in village cooperative."
        await LoanStateMachine.transition(
            db, l4, LoanStatus.REJECTED, actor=admin_user, reason=l4.rejection_reason
        )

        # Loan 5: SUBMITTED (Savitri Bai, SHG 1) - ₹15,500.00
        print("  - Creating Loan 5 (SUBMITTED awaiting approval)...")
        l5 = await _create_seed_loan(
            db, shg1.id, shg1_members[4].id, "LN-0005",
            Decimal("15500.00"), Decimal("12.000"), InterestType.REDUCING, 10,
            "Organic vegetable farming seeds and drip irrigation pipe", leader1_user.id, today + timedelta(days=15),
        )
        await LoanStateMachine.transition(db, l5, LoanStatus.SUBMITTED, actor=leader1_user, reason="Awaiting review")

        # -------------------------------------------------------------------------
        # 6. Ledger Reversal Entry (SPEC Section 16 & Section 5)
        # -------------------------------------------------------------------------
        print("6. Posting a manual error entry and executing one formal Ledger Reversal...")
        # Post a dummy misallocated fine of ₹250.00
        cash_acc = await get_account_by_code(db, shg1.id, "1000")
        fine_acc = await get_account_by_code(db, shg1.id, "4010")

        err_entry = await post_journal_entry(
            db=db,
            shg_id=shg1.id,
            entry_date=today - timedelta(days=10),
            description="Erroneous late fine entered for Kaushalya Devi during May audit",
            source_type=JournalSourceType.FINE,
            posted_by=admin_user.id,
            lines=[
                PostingLineDTO(account_id=cash_acc.id, debit=Decimal("250.00"), credit=Decimal("0.00")),
                PostingLineDTO(account_id=fine_acc.id, debit=Decimal("0.00"), credit=Decimal("250.00")),
            ],
        )
        await db.flush()

        # Officially reverse it with reason
        await reverse_journal_entry(
            db=db,
            shg_id=shg1.id,
            entry_id=err_entry.id,
            posted_by=admin_user.id,
            reason="Incorrect fine recorded during May meeting; reversed per leader request.",
        )

        await db.commit()
        print("\n[OK] Seeding complete! Database successfully populated with realistic data.")
        print_demo_logins()


def print_demo_logins() -> None:
    print("=" * 80)
    print("DEMO USER CREDENTIALS (SHG Credit Manager)")
    print("=" * 80)
    print(f"{'Role':<15} | {'Email':<22} | {'Password':<15} | {'Notes'}")
    print("-" * 80)
    print(f"{'ADMIN':<15} | {'admin@shg.org':<22} | {'AdminPass123!':<15} | Full system administrator")
    print(f"{'AUDITOR':<15} | {'auditor@shg.org':<22} | {'AuditorPass123!':<15} | Read-only auditor for both SHGs")
    print(f"{'GROUP_LEADER':<15} | {'leader1@shg.org':<22} | {'LeaderPass123!':<15} | Leader: Pragati Mahila (Rampur)")
    print(f"{'GROUP_LEADER':<15} | {'leader2@shg.org':<22} | {'LeaderPass123!':<15} | Leader: Udaan SHG (Chandpur)")
    print(f"{'MEMBER':<15} | {'member@shg.org':<22} | {'MemberPass123!':<15} | Sunita Devi (Borrower with ACTIVE loan)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(seed_data())
