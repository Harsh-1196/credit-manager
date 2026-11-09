import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models.auth import User, UserGroupAccess, UserRole
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


async def seed_data() -> None:
    async with AsyncSessionLocal() as session:
        print("Checking existing seed data...")
        admin_check = await session.execute(select(User).where(User.email == "admin@shg.org"))
        if admin_check.scalar_one_or_none():
            print("Seed data already present. Skipping.")
            return

        print("Seeding users...")
        admin_user = User(
            email="admin@shg.org",
            phone="9876543210",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        leader_user = User(
            email="leader@shg.org",
            phone="9876543211",
            password_hash=hash_password("LeaderPass123!"),
            role=UserRole.GROUP_LEADER,
            is_active=True,
        )
        auditor_user = User(
            email="auditor@shg.org",
            phone="9876543212",
            password_hash=hash_password("AuditorPass123!"),
            role=UserRole.AUDITOR,
            is_active=True,
        )
        member_user = User(
            email="member@shg.org",
            phone="9876543213",
            password_hash=hash_password("MemberPass123!"),
            role=UserRole.MEMBER,
            is_active=True,
        )

        session.add_all([admin_user, leader_user, auditor_user, member_user])
        await session.flush()

        print("Seeding SHG and group settings...")
        shg = SHG(
            name="Pragati Mahila SHG",
            village="Ramnagar",
            ward="Ward 4",
            district="Varanasi",
            formation_date=date(2025, 1, 15),
            meeting_day="1st Monday",
            meeting_frequency="MONTHLY",
            bank_account_label="SBI A/c **4589",
            status=SHGStatus.ACTIVE,
        )
        session.add(shg)
        await session.flush()

        settings = GroupSettings(
            shg_id=shg.id,
            monthly_saving_amount=Decimal("200.00"),
            late_fine_per_day=Decimal("5.00"),
            fine_grace_days=5,
            default_interest_rate=Decimal("12.000"),
            interest_type=InterestType.REDUCING,
            max_loan_multiple=Decimal("3.00"),
            min_tenure_months=3,
            max_tenure_months=24,
            processing_fee_percent=Decimal("1.000"),
            penalty_interest_rate=Decimal("2.000"),
        )
        session.add(settings)

        print("Linking group permissions...")
        leader_access = UserGroupAccess(
            user_id=leader_user.id,
            group_id=shg.id,
            access_level="LEADER",
        )
        auditor_access = UserGroupAccess(
            user_id=auditor_user.id,
            group_id=shg.id,
            access_level="AUDITOR",
        )
        session.add_all([leader_access, auditor_access])

        print("Seeding members...")
        m1 = Member(
            shg_id=shg.id,
            user_id=member_user.id,
            full_name="Sunita Devi",
            phone="9876543213",
            address="Village Ramnagar, Near Primary School",
            id_proof_type="Aadhaar",
            id_proof_last4="4512",
            date_of_birth=date(1988, 4, 12),
            joined_on=date(2025, 1, 15),
            status=MemberStatus.ACTIVE,
        )
        m2 = Member(
            shg_id=shg.id,
            user_id=None,
            full_name="Anita Sharma",
            phone="9876543214",
            address="Village Ramnagar, Main Road",
            id_proof_type="Voter ID",
            id_proof_last4="8901",
            date_of_birth=date(1991, 8, 24),
            joined_on=date(2025, 1, 15),
            status=MemberStatus.ACTIVE,
        )
        m3 = Member(
            shg_id=shg.id,
            user_id=None,
            full_name="Meena Kumari",
            phone="9876543215",
            address="Village Ramnagar, Gali No. 2",
            id_proof_type="Aadhaar",
            id_proof_last4="3321",
            date_of_birth=date(1985, 11, 3),
            joined_on=date(2025, 1, 15),
            status=MemberStatus.ACTIVE,
        )
        m4 = Member(
            shg_id=shg.id,
            user_id=None,
            full_name="Radha Bai",
            phone="9876543216",
            address="Village Ramnagar, East Tola",
            id_proof_type="Aadhaar",
            id_proof_last4="9044",
            date_of_birth=date(1993, 2, 19),
            joined_on=date(2025, 2, 1),
            status=MemberStatus.ACTIVE,
        )
        session.add_all([m1, m2, m3, m4])
        await session.flush()

        r1 = MemberRole(member_id=m1.id, role=OfficeBearerRole.PRESIDENT, from_date=date(2025, 1, 15))
        r2 = MemberRole(member_id=m2.id, role=OfficeBearerRole.SECRETARY, from_date=date(2025, 1, 15))
        r3 = MemberRole(member_id=m3.id, role=OfficeBearerRole.TREASURER, from_date=date(2025, 1, 15))
        r4 = MemberRole(member_id=m4.id, role=OfficeBearerRole.MEMBER, from_date=date(2025, 2, 1))
        session.add_all([r1, r2, r3, r4])

        await session.commit()
        print("\nSeed data successfully created!")
        print("-----------------------------------------------------------------")
        print("Demo Logins:")
        print("  ADMIN:        admin@shg.org    / AdminPass123!")
        print("  GROUP_LEADER: leader@shg.org   / LeaderPass123!")
        print("  AUDITOR:      auditor@shg.org  / AuditorPass123!")
        print("  MEMBER:       member@shg.org   / MemberPass123! (Sunita Devi)")
        print("-----------------------------------------------------------------")


if __name__ == "__main__":
    asyncio.run(seed_data())
