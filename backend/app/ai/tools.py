from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.auth import User, UserGroupAccess, UserRole
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.meetings import Meeting
from app.db.models.shg import Member
from app.domain.loans.metrics import calculate_loan_summary_figures
from app.domain.reports.service import (
    generate_group_dashboard_report,
    generate_loan_portfolio_report,
    generate_member_statement_report,
)
from app.services.meetings import get_meeting_collection_sheet


async def verify_group_access(user: User, shg_id: uuid.UUID, db: AsyncSession) -> None:
    """Enforce caller's group scope. Non-admin callers can only access assigned groups.
    Returns HTTP 404 to avoid revealing group existence outside scope."""
    if user.role == UserRole.ADMIN:
        return
    stmt = select(UserGroupAccess.id).where(
        UserGroupAccess.user_id == user.id,
        UserGroupAccess.group_id == shg_id,
    )
    result = await db.scalar(stmt)
    if not result:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404)


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[AsyncSession, User, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        db: AsyncSession,
        caller: User,
    ) -> dict[str, Any]:
        tool = self.get(name)
        if not tool:
            return {
                "status": "error",
                "error": f"Tool '{name}' is not registered.",
            }
        try:
            result = await tool.handler(db, caller, arguments)
            return {
                "status": "success",
                "data": result,
            }
        except AppError as e:
            return {
                "status": "error",
                "error": e.message,
                "code": e.code,
                "status_code": e.status_code,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to execute tool '{name}': {str(e)}",
            }


registry = ToolRegistry()


# -----------------------------------------------------------------------------
# Tool 1: get_member_statement
# -----------------------------------------------------------------------------
async def handle_get_member_statement(
    db: AsyncSession,
    caller: User,
    args: dict[str, Any],
) -> dict[str, Any]:
    member_id_raw = args.get("member_id")
    if not member_id_raw:
        raise AppError(code="VALIDATION_ERROR", message="member_id is required.", status_code=422)

    try:
        member_id = uuid.UUID(str(member_id_raw))
    except ValueError:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404) from None

    # Fetch member to verify scope
    stmt = select(Member).where(Member.id == member_id)
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if not member:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404)

    # Scoping: If caller is MEMBER, can only access their own statement
    if caller.role == UserRole.MEMBER:
        if member.user_id != caller.id:
            raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404)
    else:
        # Group leader / auditor: check group access
        await verify_group_access(caller, member.shg_id, db)

    report = await generate_member_statement_report(db, member_id)
    return {
        "member_name": report.member.name,
        "member_id": str(report.member.member_id),
        "shg_name": report.member.shg_name,
        "status": report.member.status,
        "join_date": report.member.join_date,
        "total_savings_balance": report.member.total_savings_balance,
        "current_outstanding_principal": report.member.current_outstanding_principal,
        "active_loans": [
            {
                "loan_number": loan_item.get("loan_number"),
                "principal": str(loan_item.get("principal")),
                "outstanding_principal": str(loan_item.get("outstanding_principal")),
                "interest_rate": str(loan_item.get("interest_rate")),
                "status": str(loan_item.get("status")),
            }
            for loan_item in report.active_loans
        ],
        "passbook_recent": [
            {
                "date": p.get("date"),
                "particulars": p.get("particulars"),
                "debit": str(p.get("debit")),
                "credit": str(p.get("credit")),
                "balance": str(p.get("balance")),
            }
            for p in report.passbook_entries[:5]
        ],
    }


registry.register(
    ToolDefinition(
        name="get_member_statement",
        description="Retrieve the financial statement, savings balance, outstanding loans, and recent passbook entries for a specific member. Scoped to authorized callers only.",
        parameters={
            "type": "object",
            "properties": {
                "member_id": {
                    "type": "string",
                    "description": "UUID of the member whose statement is requested.",
                }
            },
            "required": ["member_id"],
        },
        handler=handle_get_member_statement,
    )
)


# -----------------------------------------------------------------------------
# Tool 2: list_overdue
# -----------------------------------------------------------------------------
async def handle_list_overdue(
    db: AsyncSession,
    caller: User,
    args: dict[str, Any],
) -> dict[str, Any]:
    shg_id_raw = args.get("shg_id")
    if not shg_id_raw:
        raise AppError(code="VALIDATION_ERROR", message="shg_id is required.", status_code=422)

    try:
        shg_id = uuid.UUID(str(shg_id_raw))
    except ValueError:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404) from None

    # Scoping: Members cannot list delinquencies of other group members
    if caller.role == UserRole.MEMBER:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404)

    await verify_group_access(caller, shg_id, db)

    # Query overdue loans and schedules
    today = date.today()
    stmt = (
        select(Loan, Member)
        .join(Member, Loan.member_id == Member.id)
        .where(Loan.shg_id == shg_id, Loan.status == LoanStatus.OVERDUE)
    )
    res = await db.execute(stmt)
    rows = res.all()

    overdue_loans = []
    for loan, member in rows:
        figs = await calculate_loan_summary_figures(db, loan, as_of_date=today)
        # Check overdue schedule installments
        sch_stmt = select(LoanSchedule).where(
            LoanSchedule.loan_id == loan.id,
            LoanSchedule.status.in_([LoanScheduleStatus.OVERDUE, LoanScheduleStatus.PARTIAL]),
        )
        sch_res = await db.execute(sch_stmt)
        schedules = sch_res.scalars().all()

        max_days = figs.days_overdue
        total_arrears = Decimal("0.00")
        for sch in schedules:
            if sch.due_date < today:
                unpaid = (sch.principal_due - sch.principal_paid) + (sch.interest_due - sch.interest_paid)
                if unpaid > 0:
                    total_arrears += unpaid

        overdue_loans.append(
            {
                "loan_id": str(loan.id),
                "loan_number": loan.loan_number,
                "borrower_name": member.full_name,
                "outstanding_principal": str(figs.outstanding_principal),
                "days_overdue": max_days,
                "overdue_arrears": f"{total_arrears:.2f}",
                "status": loan.status.value,
            }
        )

    return {
        "shg_id": str(shg_id),
        "overdue_count": len(overdue_loans),
        "overdue_loans": overdue_loans,
    }


registry.register(
    ToolDefinition(
        name="list_overdue",
        description="List all members with delinquent or overdue loans in a Self-Help Group, including days past due and arrears. Restricted to Leaders, Auditors, and Admins.",
        parameters={
            "type": "object",
            "properties": {
                "shg_id": {
                    "type": "string",
                    "description": "UUID of the Self-Help Group to check for overdue loans.",
                }
            },
            "required": ["shg_id"],
        },
        handler=handle_list_overdue,
    )
)


# -----------------------------------------------------------------------------
# Tool 3: get_par_report
# -----------------------------------------------------------------------------
async def handle_get_par_report(
    db: AsyncSession,
    caller: User,
    args: dict[str, Any],
) -> dict[str, Any]:
    shg_id_raw = args.get("shg_id")
    if not shg_id_raw:
        raise AppError(code="VALIDATION_ERROR", message="shg_id is required.", status_code=422)

    try:
        shg_id = uuid.UUID(str(shg_id_raw))
    except ValueError:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404) from None

    if caller.role == UserRole.MEMBER:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404)

    await verify_group_access(caller, shg_id, db)

    portfolio = await generate_loan_portfolio_report(db, shg_id)
    return {
        "shg_id": str(shg_id),
        "shg_name": portfolio.shg_name,
        "as_of_date": portfolio.as_of_date,
        "active_loans_count": portfolio.metrics.get("active_loans_count", 0),
        "total_disbursed_principal": str(portfolio.metrics.get("total_disbursed_principal", "0.00")),
        "total_outstanding_principal": str(portfolio.metrics.get("total_outstanding_principal", "0.00")),
        "total_overdue_principal": str(portfolio.metrics.get("total_overdue_principal", "0.00")),
        "par_30": f"{portfolio.metrics.get('par_30_ratio', '0.00')}%",
        "par_60": f"{portfolio.metrics.get('par_60_ratio', '0.00')}%",
        "par_90": f"{portfolio.metrics.get('par_90_ratio', '0.00')}%",
        "aging_buckets": [
            {
                "bucket": b.bucket,
                "count": b.count,
                "amount": b.amount,
            }
            for b in portfolio.aging_buckets
        ],
    }


registry.register(
    ToolDefinition(
        name="get_par_report",
        description="Retrieve Portfolio At Risk (PAR 30, PAR 60, PAR 90) metrics and aging delinquency buckets for a Self-Help Group. Restricted to Leaders, Auditors, and Admins.",
        parameters={
            "type": "object",
            "properties": {
                "shg_id": {
                    "type": "string",
                    "description": "UUID of the Self-Help Group.",
                }
            },
            "required": ["shg_id"],
        },
        handler=handle_get_par_report,
    )
)


# -----------------------------------------------------------------------------
# Tool 4: get_group_dashboard
# -----------------------------------------------------------------------------
async def handle_get_group_dashboard(
    db: AsyncSession,
    caller: User,
    args: dict[str, Any],
) -> dict[str, Any]:
    shg_id_raw = args.get("shg_id")
    if not shg_id_raw:
        raise AppError(code="VALIDATION_ERROR", message="shg_id is required.", status_code=422)

    try:
        shg_id = uuid.UUID(str(shg_id_raw))
    except ValueError:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404) from None

    if caller.role == UserRole.MEMBER:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404)

    await verify_group_access(caller, shg_id, db)

    report = await generate_group_dashboard_report(db, shg_id)
    return {
        "shg_id": str(shg_id),
        "shg_name": report.shg_name,
        "as_of_date": report.as_of_date,
        "total_corpus": report.figures.total_corpus,
        "total_savings": report.figures.total_savings,
        "outstanding_principal": report.figures.outstanding_principal,
        "repayment_rate": f"{report.figures.repayment_rate}%",
        "overdue_amount": report.figures.overdue_amount,
        "next_meeting_date": report.figures.next_meeting_date,
        "collections_due_count": len(report.collections_due),
    }


registry.register(
    ToolDefinition(
        name="get_group_dashboard",
        description="Fetch key headline financial figures for a Self-Help Group: total corpus, savings, outstanding principal, repayment rate, and overdue amount. Restricted to Leaders, Auditors, and Admins.",
        parameters={
            "type": "object",
            "properties": {
                "shg_id": {
                    "type": "string",
                    "description": "UUID of the Self-Help Group.",
                }
            },
            "required": ["shg_id"],
        },
        handler=handle_get_group_dashboard,
    )
)


# -----------------------------------------------------------------------------
# Tool 5: get_collection_sheet
# -----------------------------------------------------------------------------
async def handle_get_collection_sheet(
    db: AsyncSession,
    caller: User,
    args: dict[str, Any],
) -> dict[str, Any]:
    meeting_id_raw = args.get("meeting_id")
    if not meeting_id_raw:
        raise AppError(code="VALIDATION_ERROR", message="meeting_id is required.", status_code=422)

    try:
        meeting_id = uuid.UUID(str(meeting_id_raw))
    except ValueError:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404) from None

    # Check meeting existence and scope
    m_stmt = select(Meeting).where(Meeting.id == meeting_id)
    m_res = await db.execute(m_stmt)
    meeting = m_res.scalar_one_or_none()
    if not meeting:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404)

    if caller.role == UserRole.MEMBER:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404)

    await verify_group_access(caller, meeting.shg_id, db)

    sheet = await get_meeting_collection_sheet(db, meeting_id, meeting.shg_id)
    return {
        "meeting_id": str(meeting_id),
        "shg_id": str(sheet.shg_id),
        "meeting_date": str(sheet.meeting_date),
        "total_expected_savings": str(sheet.totals.total_savings_due),
        "total_expected_loan_repayment": str(sheet.totals.total_emi_due),
        "total_expected_collection": str(sheet.totals.total_due),
        "members_count": len(sheet.members),
        "member_dues_sample": [
            {
                "member_name": m.member_name,
                "savings_due": str(m.savings_due),
                "loan_emi_due": str(m.emi_due),
                "total_due": str(m.total_due),
            }
            for m in sheet.members[:5]
        ],
    }


registry.register(
    ToolDefinition(
        name="get_collection_sheet",
        description="Retrieve the collection sheet for a scheduled SHG meeting, detailing expected member dues (savings, EMI installments, arrears, fines). Restricted to Leaders, Auditors, and Admins.",
        parameters={
            "type": "object",
            "properties": {
                "meeting_id": {
                    "type": "string",
                    "description": "UUID of the meeting.",
                }
            },
            "required": ["meeting_id"],
        },
        handler=handle_get_collection_sheet,
    )
)
