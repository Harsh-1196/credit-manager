import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.ledger import Account, AccountType
from app.db.models.shg import Member

STANDARD_CHART_OF_ACCOUNTS: list[tuple[str, str, AccountType]] = [
    ("1000", "Cash in Hand", AccountType.ASSET),
    ("1010", "Bank Balance", AccountType.ASSET),
    ("1100", "Member Loans Receivable", AccountType.ASSET),
    ("1110", "Interest Receivable", AccountType.ASSET),
    ("2000", "Member Savings", AccountType.LIABILITY),
    ("2100", "External / Bank Linkage Loan", AccountType.LIABILITY),
    ("3000", "Group Corpus / Retained Surplus", AccountType.EQUITY),
    ("4000", "Interest Income", AccountType.INCOME),
    ("4010", "Fine and Penalty Income", AccountType.INCOME),
    ("4020", "Processing Fee Income", AccountType.INCOME),
    ("5000", "Operating Expenses", AccountType.EXPENSE),
    ("5010", "Loan Write-offs", AccountType.EXPENSE),
]


async def initialize_shg_chart_of_accounts(
    db: AsyncSession,
    shg_id: uuid.UUID,
) -> dict[str, Account]:
    """
    Auto-creates the per-SHG chart of accounts from SPEC section 5.
    Safe to call multiple times (idempotent).
    """
    stmt = select(Account).where(Account.shg_id == shg_id, Account.member_id.is_(None))
    res = await db.execute(stmt)
    existing_accounts = {acc.code: acc for acc in res.scalars().all()}

    created: dict[str, Account] = {}
    for code, name, acc_type in STANDARD_CHART_OF_ACCOUNTS:
        if code in existing_accounts:
            created[code] = existing_accounts[code]
        else:
            acc = Account(
                shg_id=shg_id,
                code=code,
                name=name,
                type=acc_type,
                member_id=None,
                is_active=True,
            )
            db.add(acc)
            created[code] = acc

    await db.flush()
    return created


async def get_or_create_member_sub_accounts(
    db: AsyncSession,
    shg_id: uuid.UUID,
    member: Member,
) -> tuple[Account, Account]:
    """
    Creates or retrieves member-specific sub-accounts:
    - 2000-{id[:8]}: Member Savings (LIABILITY)
    - 1100-{id[:8]}: Member Loans Receivable (ASSET)
    """
    suffix = str(member.id)[:8]
    savings_code = f"2000-{suffix}"
    loan_code = f"1100-{suffix}"

    stmt = select(Account).where(
        Account.shg_id == shg_id,
        Account.code.in_([savings_code, loan_code]),
    )
    res = await db.execute(stmt)
    existing = {acc.code: acc for acc in res.scalars().all()}

    savings_acc = existing.get(savings_code)
    if not savings_acc:
        savings_acc = Account(
            shg_id=shg_id,
            code=savings_code,
            name=f"Member Savings - {member.full_name}",
            type=AccountType.LIABILITY,
            member_id=member.id,
            is_active=True,
        )
        db.add(savings_acc)

    loan_acc = existing.get(loan_code)
    if not loan_acc:
        loan_acc = Account(
            shg_id=shg_id,
            code=loan_code,
            name=f"Member Loans Receivable - {member.full_name}",
            type=AccountType.ASSET,
            member_id=member.id,
            is_active=True,
        )
        db.add(loan_acc)

    await db.flush()
    return savings_acc, loan_acc


async def get_account_by_code(
    db: AsyncSession,
    shg_id: uuid.UUID,
    code: str,
) -> Account:
    """Fetch an account by code for an SHG, raising 404 if missing."""
    stmt = select(Account).where(Account.shg_id == shg_id, Account.code == code, Account.is_active.is_(True))
    res = await db.execute(stmt)
    account = res.scalar_one_or_none()
    if not account:
        raise AppError(
            code="ACCOUNT_NOT_FOUND",
            message=f"Account with code '{code}' not found in group chart of accounts.",
            status_code=404,
            details={"shg_id": str(shg_id), "code": code},
        )
    return account
