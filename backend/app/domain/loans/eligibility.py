import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import money_to_str, quantize_money
from app.db.models.ledger import Account, JournalEntry, JournalLine
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.shg import GroupSettings, Member, MemberStatus
from app.domain.savings.service import get_member_savings_balance


@dataclass(frozen=True)
class EligibilityCheckItem:
    code: str
    name: str
    passed: bool
    severity: str  # "BLOCKER" | "WARNING" | "INFO"
    message: str
    actual_value: str | None = None
    threshold_value: str | None = None


@dataclass(frozen=True)
class EligibilityEvaluationResult:
    is_eligible: bool
    checks: list[EligibilityCheckItem]
    has_warnings: bool
    summary_message: str


async def get_group_available_cash(db: AsyncSession, shg_id: uuid.UUID) -> Decimal:
    """
    Computes available liquid cash (Account 1000: Cash in Hand + Account 1010: Bank Account)
    for the group from the double-entry general ledger.
    Assets have normal debit balance: balance = sum(debit) - sum(credit).
    """
    stmt = (
        select(
            func.coalesce(func.sum(JournalLine.debit), Decimal("0.00"))
            - func.coalesce(func.sum(JournalLine.credit), Decimal("0.00"))
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(Account, JournalLine.account_id == Account.id)
        .where(
            JournalEntry.shg_id == shg_id,
            Account.shg_id == shg_id,
            Account.code.in_(["1000", "1010"]),
        )
    )
    res = await db.execute(stmt)
    cash = res.scalar()
    return quantize_money(cash if cash is not None else Decimal("0.00"))


async def evaluate_loan_eligibility(
    db: AsyncSession,
    shg_id: uuid.UUID,
    member_id: uuid.UUID,
    principal: Decimal,
    tenure_months: int,
    exclude_loan_id: uuid.UUID | None = None,
) -> EligibilityEvaluationResult:
    """
    Evaluates loan eligibility checks as specified in SPEC 6.2:
    1. Member is active in the group (BLOCKER)
    2. No concurrent active/pending loans (BLOCKER)
    3. Requested principal <= max_loan_multiple * member savings balance (BLOCKER)
    4. Requested principal <= available group cash (WARNING for approver)
    5. Tenure within min_tenure_months and max_tenure_months (BLOCKER)
    6. No overdue installments on existing loans (BLOCKER)
    """
    principal = quantize_money(principal)
    checks: list[EligibilityCheckItem] = []

    # 1. Fetch Member
    member_stmt = select(Member).where(Member.id == member_id, Member.shg_id == shg_id)
    member_res = await db.execute(member_stmt)
    member = member_res.scalar_one_or_none()

    if not member or member.status != MemberStatus.ACTIVE:
        status_str = member.status.value if member else "NOT_FOUND"
        checks.append(
            EligibilityCheckItem(
                code="MEMBER_ACTIVE",
                name="Active Member Status",
                passed=False,
                severity="BLOCKER",
                message=f"Member must be ACTIVE in the group. Current status is {status_str}.",
                actual_value=status_str,
                threshold_value="ACTIVE",
            )
        )
    else:
        checks.append(
            EligibilityCheckItem(
                code="MEMBER_ACTIVE",
                name="Active Member Status",
                passed=True,
                severity="BLOCKER",
                message="Member is in good standing and actively enrolled in the group.",
                actual_value=member.status.value,
                threshold_value="ACTIVE",
            )
        )

    # 2. Fetch Group Settings
    settings_stmt = select(GroupSettings).where(GroupSettings.shg_id == shg_id)
    settings_res = await db.execute(settings_stmt)
    settings = settings_res.scalar_one_or_none()

    min_tenure = settings.min_tenure_months if settings else 3
    max_tenure = settings.max_tenure_months if settings else 24
    max_multiple = settings.max_loan_multiple if settings else Decimal("3.00")

    # 3. Check Concurrent Active Loans
    concurrent_statuses = [
        LoanStatus.SUBMITTED,
        LoanStatus.APPROVED,
        LoanStatus.DISBURSED,
        LoanStatus.ACTIVE,
        LoanStatus.OVERDUE,
    ]
    active_loans_stmt = select(func.count()).select_from(Loan).where(
        Loan.shg_id == shg_id,
        Loan.member_id == member_id,
        Loan.status.in_(concurrent_statuses),
    )
    if exclude_loan_id:
        active_loans_stmt = active_loans_stmt.where(Loan.id != exclude_loan_id)

    active_count_res = await db.execute(active_loans_stmt)
    active_loans_count = active_count_res.scalar() or 0

    if active_loans_count > 0:
        checks.append(
            EligibilityCheckItem(
                code="CONCURRENT_LOANS",
                name="Concurrent Active Loans Limit",
                passed=False,
                severity="BLOCKER",
                message=f"Member already has {active_loans_count} active or pending loan(s). Limit is 1 loan per member.",
                actual_value=str(active_loans_count),
                threshold_value="0",
            )
        )
    else:
        checks.append(
            EligibilityCheckItem(
                code="CONCURRENT_LOANS",
                name="Concurrent Active Loans Limit",
                passed=True,
                severity="BLOCKER",
                message="Member has no concurrent active or pending loans.",
                actual_value="0",
                threshold_value="0",
            )
        )

    # 4. Check Savings Multiple Cap
    savings_balance = await get_member_savings_balance(db, shg_id, member_id)
    max_allowed_principal = quantize_money(savings_balance * max_multiple)

    if principal > max_allowed_principal:
        checks.append(
            EligibilityCheckItem(
                code="SAVINGS_MULTIPLE",
                name="Savings Multiple Borrowing Cap",
                passed=False,
                severity="BLOCKER",
                message=(
                    f"Requested principal (₹{money_to_str(principal)}) exceeds maximum allowed "
                    f"multiple of {max_multiple}x savings balance (₹{money_to_str(max_allowed_principal)})."
                ),
                actual_value=money_to_str(principal),
                threshold_value=money_to_str(max_allowed_principal),
            )
        )
    else:
        checks.append(
            EligibilityCheckItem(
                code="SAVINGS_MULTIPLE",
                name="Savings Multiple Borrowing Cap",
                passed=True,
                severity="BLOCKER",
                message=(
                    f"Principal is within the {max_multiple}x savings cap "
                    f"(Eligible limit: ₹{money_to_str(max_allowed_principal)})."
                ),
                actual_value=money_to_str(principal),
                threshold_value=money_to_str(max_allowed_principal),
            )
        )

    # 5. Check Group Cash Liquidity (WARNING, not hard block per SPEC 6.2)
    group_cash = await get_group_available_cash(db, shg_id)
    if principal > group_cash:
        checks.append(
            EligibilityCheckItem(
                code="GROUP_CASH_LIQUIDITY",
                name="Group Cash Liquidity",
                passed=False,
                severity="WARNING",
                message=(
                    f"Requested loan amount (₹{money_to_str(principal)}) exceeds currently available "
                    f"group liquid cash (₹{money_to_str(group_cash)}). Disbursal may require upcoming collections."
                ),
                actual_value=money_to_str(group_cash),
                threshold_value=money_to_str(principal),
            )
        )
    else:
        checks.append(
            EligibilityCheckItem(
                code="GROUP_CASH_LIQUIDITY",
                name="Group Cash Liquidity",
                passed=True,
                severity="WARNING",
                message=f"Group has sufficient liquid funds (₹{money_to_str(group_cash)}) to disburse this loan.",
                actual_value=money_to_str(group_cash),
                threshold_value=money_to_str(principal),
            )
        )

    # 6. Check Tenure Range
    if tenure_months < min_tenure or tenure_months > max_tenure:
        checks.append(
            EligibilityCheckItem(
                code="TENURE_RANGE",
                name="Tenure Policy Alignment",
                passed=False,
                severity="BLOCKER",
                message=f"Tenure of {tenure_months} months must be between {min_tenure} and {max_tenure} months.",
                actual_value=f"{tenure_months} months",
                threshold_value=f"{min_tenure} - {max_tenure} months",
            )
        )
    else:
        checks.append(
            EligibilityCheckItem(
                code="TENURE_RANGE",
                name="Tenure Policy Alignment",
                passed=True,
                severity="BLOCKER",
                message=f"Tenure of {tenure_months} months complies with group policy ({min_tenure} - {max_tenure} months).",
                actual_value=f"{tenure_months} months",
                threshold_value=f"{min_tenure} - {max_tenure} months",
            )
        )

    # 7. Check Overdue Installments on Any Past/Existing Loans
    overdue_stmt = (
        select(func.count())
        .select_from(LoanSchedule)
        .join(Loan, LoanSchedule.loan_id == Loan.id)
        .where(
            Loan.shg_id == shg_id,
            Loan.member_id == member_id,
            LoanSchedule.status == LoanScheduleStatus.OVERDUE,
        )
    )
    overdue_res = await db.execute(overdue_stmt)
    overdue_count = overdue_res.scalar() or 0

    if overdue_count > 0:
        checks.append(
            EligibilityCheckItem(
                code="NO_OVERDUE_ARREARS",
                name="Existing Repayment Track Record",
                passed=False,
                severity="BLOCKER",
                message=f"Member has {overdue_count} overdue installment(s) in arrears on previous loans.",
                actual_value=f"{overdue_count} overdue",
                threshold_value="0 overdue",
            )
        )
    else:
        checks.append(
            EligibilityCheckItem(
                code="NO_OVERDUE_ARREARS",
                name="Existing Repayment Track Record",
                passed=True,
                severity="BLOCKER",
                message="No overdue loan installments or repayment arrears found.",
                actual_value="0 overdue",
                threshold_value="0 overdue",
            )
        )

    # Compute overall eligibility
    blocker_failures = [c for c in checks if c.severity == "BLOCKER" and not c.passed]
    warning_failures = [c for c in checks if c.severity == "WARNING" and not c.passed]

    is_eligible = len(blocker_failures) == 0
    has_warnings = len(warning_failures) > 0

    if not is_eligible:
        summary_message = f"Ineligible: {len(blocker_failures)} policy criteria not met."
    elif has_warnings:
        summary_message = "Eligible with warning: Cash liquidity review recommended for approver."
    else:
        summary_message = "Fully eligible: All policy and risk criteria passed."

    return EligibilityEvaluationResult(
        is_eligible=is_eligible,
        checks=checks,
        has_warnings=has_warnings,
        summary_message=summary_message,
    )
