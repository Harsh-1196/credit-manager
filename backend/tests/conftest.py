import os
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db import models as _models  # noqa: F401
from app.db.base import Base
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
from app.db.session import get_db
from app.domain.ledger.accounts import get_or_create_member_sub_accounts, initialize_shg_chart_of_accounts
from app.main import app

POSTGRES_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/shg_test",
)


def get_test_engine_and_maker() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession], str]:
    db_url = os.environ.get("TEST_DATABASE_URL")

    if db_url and "postgresql" in db_url:
        selected_url = db_url
        engine = create_async_engine(selected_url, echo=False)
    else:
        # Fallback to in-memory sqlite when Postgres test database is not configured/reachable
        selected_url = "sqlite+aiosqlite:///:memory:"
        engine = create_async_engine(
            selected_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return engine, session_maker, selected_url


test_engine, TestingSessionLocal, active_db_url = get_test_engine_and_maker()


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database() -> AsyncGenerator[None, None]:
    """Create all schema tables at test start and drop at end."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session per test."""
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Test HTTP client with overridden get_db dependency."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email="admin@test.org",
        phone="9876543210",
        password_hash=hash_password("admin_password_123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user: User) -> str:
    return create_access_token(subject=str(admin_user.id), role=admin_user.role.value)


@pytest.fixture
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def leader_user(db_session: AsyncSession) -> User:
    user = User(
        email="leader@test.org",
        phone="9876543211",
        password_hash=hash_password("leader_password_123"),
        role=UserRole.GROUP_LEADER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def leader_token(leader_user: User) -> str:
    return create_access_token(subject=str(leader_user.id), role=leader_user.role.value)


@pytest.fixture
def leader_headers(leader_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {leader_token}"}


@pytest_asyncio.fixture
async def auditor_user(db_session: AsyncSession) -> User:
    user = User(
        email="auditor@test.org",
        phone="9876543212",
        password_hash=hash_password("auditor_password_123"),
        role=UserRole.AUDITOR,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auditor_token(auditor_user: User) -> str:
    return create_access_token(subject=str(auditor_user.id), role=auditor_user.role.value)


@pytest.fixture
def auditor_headers(auditor_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auditor_token}"}


@pytest_asyncio.fixture
async def member_user(db_session: AsyncSession) -> User:
    user = User(
        email="member@test.org",
        phone="9876543213",
        password_hash=hash_password("member_password_123"),
        role=UserRole.MEMBER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def member_token(member_user: User) -> str:
    return create_access_token(subject=str(member_user.id), role=member_user.role.value)


@pytest.fixture
def member_headers(member_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {member_token}"}


@pytest_asyncio.fixture
async def test_group(
    db_session: AsyncSession,
    leader_user: User,
    auditor_user: User,
    member_user: User,
) -> SHG:
    shg = SHG(
        name="Assigned Test SHG",
        village="Village A",
        district="District 1",
        formation_date=date(2025, 1, 1),
        meeting_day="Monday",
        meeting_frequency="MONTHLY",
        status=SHGStatus.ACTIVE,
    )
    db_session.add(shg)
    await db_session.flush()

    settings = GroupSettings(
        shg_id=shg.id,
        monthly_saving_amount=Decimal("200.00"),
        late_fine_per_day=Decimal("5.00"),
        fine_grace_days=5,
        default_interest_rate=Decimal("12.000"),
        interest_type=InterestType.REDUCING,
    )
    db_session.add(settings)

    # Link leader and auditor access
    db_session.add(UserGroupAccess(user_id=leader_user.id, group_id=shg.id, access_level="LEADER"))
    db_session.add(UserGroupAccess(user_id=auditor_user.id, group_id=shg.id, access_level="AUDITOR"))

    # Add member linked to member_user
    member = Member(
        shg_id=shg.id,
        user_id=member_user.id,
        full_name="Member Sunita",
        phone="9876543213",
        address="House 1, Village A",
        id_proof_type="Aadhaar",
        id_proof_last4="1234",
        joined_on=date(2025, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(member)
    await db_session.flush()

    db_session.add(MemberRole(member_id=member.id, role=OfficeBearerRole.MEMBER, from_date=date(2025, 1, 1)))

    # Initialize ledger accounts
    await initialize_shg_chart_of_accounts(db_session, shg.id)
    await get_or_create_member_sub_accounts(db_session, shg.id, member)

    await db_session.commit()
    await db_session.refresh(shg)
    return shg


@pytest_asyncio.fixture
async def other_group(db_session: AsyncSession) -> SHG:
    """Group that leader, auditor, and member do NOT have access to."""
    shg = SHG(
        name="Unassigned Other SHG",
        village="Village B",
        district="District 2",
        formation_date=date(2025, 2, 1),
        meeting_day="Wednesday",
        meeting_frequency="MONTHLY",
        status=SHGStatus.ACTIVE,
    )
    db_session.add(shg)
    await db_session.flush()

    settings = GroupSettings(
        shg_id=shg.id,
        monthly_saving_amount=Decimal("300.00"),
        late_fine_per_day=Decimal("10.00"),
        fine_grace_days=3,
        default_interest_rate=Decimal("15.000"),
        interest_type=InterestType.FLAT,
    )
    db_session.add(settings)

    member = Member(
        shg_id=shg.id,
        user_id=None,
        full_name="Other Member",
        phone="9876543299",
        address="House 9, Village B",
        id_proof_type="Voter ID",
        id_proof_last4="9999",
        joined_on=date(2025, 2, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(member)

    await db_session.commit()
    await db_session.refresh(shg)
    return shg


@pytest_asyncio.fixture
async def funded_group_fixture(db_session: AsyncSession, admin_user: User) -> dict:
    """
    Sets up an SHG with chart of accounts, funded Cash in Hand (₹50,000),
    and two members (one leader, one borrower).
    """
    from app.db.models.ledger import JournalSourceType
    from app.domain.ledger.posting import PostingLineDTO, post_journal_entry

    shg = SHG(
        name="Ekta Mahila Mandal",
        village="Kashi",
        district="Varanasi",
        formation_date=date(2024, 1, 1),
        meeting_day="WEDNESDAY",
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
        processing_fee_percent=Decimal("1.000"),
        penalty_interest_rate=Decimal("2.000"),
        fine_grace_days=5,
        prepayment_policy="REDUCE_TENURE",
    )
    db_session.add(settings)

    # Leader User
    leader_user = User(
        email="leader_ekta@shg.org",
        password_hash="hash",
        phone="9876543201",
        role=UserRole.GROUP_LEADER,
    )
    db_session.add(leader_user)
    await db_session.flush()
    db_session.add(UserGroupAccess(user_id=leader_user.id, group_id=shg.id))

    # Borrower User
    borrower_user = User(
        email="borrower_ekta@shg.org",
        password_hash="hash",
        phone="9876543202",
        role=UserRole.MEMBER,
    )
    db_session.add(borrower_user)
    await db_session.flush()
    db_session.add(UserGroupAccess(user_id=borrower_user.id, group_id=shg.id))

    # Member Record
    borrower_member = Member(
        shg_id=shg.id,
        user_id=borrower_user.id,
        full_name="Meera Bai",
        phone="9876543202",
        joined_on=date(2024, 1, 1),
        status=MemberStatus.ACTIVE,
    )
    db_session.add(borrower_member)

    # Initialize Chart of Accounts
    accounts = await initialize_shg_chart_of_accounts(db_session, shg.id)
    cash_acc = accounts["1000"]
    corpus_acc = accounts["3000"]

    # Fund the Cash account with ₹50,000 from Group Corpus
    await post_journal_entry(
        db=db_session,
        shg_id=shg.id,
        entry_date=date(2026, 1, 1),
        description="Initial Group Corpus Funding",
        source_type=JournalSourceType.ADJUSTMENT,
        lines=[
            PostingLineDTO(account_id=cash_acc.id, debit=Decimal("50000.00"), credit=Decimal("0.00")),
            PostingLineDTO(account_id=corpus_acc.id, debit=Decimal("0.00"), credit=Decimal("50000.00")),
        ],
        posted_by=admin_user.id,
    )

    await db_session.commit()
    return {
        "shg": shg,
        "leader": leader_user,
        "borrower": borrower_user,
        "member": borrower_member,
        "cash_acc": cash_acc,
    }
