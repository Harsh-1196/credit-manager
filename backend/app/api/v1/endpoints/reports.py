from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.errors import AppError
from app.db.models.auth import User, UserRole
from app.db.models.meetings import Meeting
from app.db.models.shg import Member
from app.domain.reports.schemas import (
    GroupDashboardReportResponse,
    GroupLedgerReportResponse,
    LoanPortfolioReportResponse,
    MemberStatementReportResponse,
)
from app.domain.reports.service import (
    export_report_to_csv,
    generate_group_dashboard_report,
    generate_group_ledger_report,
    generate_loan_portfolio_report,
    generate_member_statement_report,
)
from app.services.meetings import get_meeting_collection_sheet

router = APIRouter()


def check_group_access(user: User, shg_id: uuid.UUID) -> None:
    if user.role == UserRole.ADMIN:
        return
    permitted_ids = [ga.group_id for ga in (getattr(user, "group_access", None) or [])]
    if shg_id not in permitted_ids:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=status.HTTP_404_NOT_FOUND)


@router.get(
    "/group-dashboard",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/csv": {},
            }
        }
    },
)
async def get_group_dashboard_report(
    shg_id: uuid.UUID = Query(..., description="Target Self-Help Group UUID"),
    as_of_date: date | None = Query(None, description="Report calculation date"),
    format: Literal["json", "csv"] = Query("json", description="Output format"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response | GroupDashboardReportResponse:
    if current_user.role == UserRole.MEMBER:
        raise AppError(
            code="UNAUTHORIZED",
            message="Members cannot view group-wide dashboard reports. Use member-statement instead.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    check_group_access(current_user, shg_id)

    report = await generate_group_dashboard_report(db, shg_id=shg_id, as_of_date=as_of_date)

    if format == "csv":
        csv_data = export_report_to_csv("group-dashboard", report.model_dump())
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="group_dashboard_{shg_id}.csv"'},
        )

    return report


@router.get(
    "/member-statement",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/csv": {},
            }
        }
    },
)
async def get_member_statement_report(
    member_id: uuid.UUID = Query(..., description="Target Member UUID"),
    from_date: date | None = Query(None, description="Start date"),
    to_date: date | None = Query(None, description="End date"),
    format: Literal["json", "csv"] = Query("json", description="Output format"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response | MemberStatementReportResponse:
    member = await db.get(Member, member_id)
    if not member:
        raise AppError(code="MEMBER_NOT_FOUND", message=f"Member {member_id} not found", status_code=404)

    # Role-aware permission check
    if current_user.role == UserRole.MEMBER:
        if member.user_id != current_user.id:
            raise AppError(
                code="UNAUTHORIZED",
                message="Members may only view their own personal member statement.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
    else:
        check_group_access(current_user, member.shg_id)

    report = await generate_member_statement_report(
        db, member_id=member_id, from_date=from_date, to_date=to_date
    )

    if format == "csv":
        csv_data = export_report_to_csv("member-statement", report.model_dump())
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="member_statement_{member_id}.csv"'},
        )

    return report


@router.get(
    "/group-ledger",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/csv": {},
            }
        }
    },
)
async def get_group_ledger_report(
    shg_id: uuid.UUID = Query(..., description="Target Self-Help Group UUID"),
    from_date: date | None = Query(None, description="Start date"),
    to_date: date | None = Query(None, description="End date"),
    account_code: str | None = Query(None, description="Filter by account code prefix"),
    format: Literal["json", "csv"] = Query("json", description="Output format"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response | GroupLedgerReportResponse:
    if current_user.role == UserRole.MEMBER:
        raise AppError(
            code="UNAUTHORIZED",
            message="Members cannot access full group double-entry ledgers.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    check_group_access(current_user, shg_id)

    report = await generate_group_ledger_report(
        db, shg_id=shg_id, from_date=from_date, to_date=to_date, account_code=account_code
    )

    if format == "csv":
        csv_data = export_report_to_csv("group-ledger", report.model_dump())
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="group_ledger_{shg_id}.csv"'},
        )

    return report


@router.get(
    "/loan-portfolio",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/csv": {},
            }
        }
    },
)
async def get_loan_portfolio_report(
    shg_id: uuid.UUID | None = Query(None, description="Target Self-Help Group UUID"),
    as_of_date: date | None = Query(None, description="Report date"),
    format: Literal["json", "csv"] = Query("json", description="Output format"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response | LoanPortfolioReportResponse:
    if current_user.role == UserRole.MEMBER:
        raise AppError(
            code="UNAUTHORIZED",
            message="Members cannot view group portfolio reports.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if shg_id:
        check_group_access(current_user, shg_id)

    report = await generate_loan_portfolio_report(db, shg_id=shg_id, as_of_date=as_of_date)

    if format == "csv":
        csv_data = export_report_to_csv("loan-portfolio", report.model_dump())
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="loan_portfolio.csv"'},
        )

    return report


@router.get(
    "/collection-sheet",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/csv": {},
            }
        }
    },
)
async def get_collection_sheet_report(
    meeting_id: uuid.UUID = Query(..., description="Target Meeting UUID"),
    format: Literal["json", "csv"] = Query("json", description="Output format"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response | dict:
    if current_user.role == UserRole.MEMBER:
        raise AppError(
            code="UNAUTHORIZED",
            message="Members cannot access administrative meeting collection sheets.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    stmt_m = select(Meeting).where(Meeting.id == meeting_id)
    meeting = (await db.execute(stmt_m)).scalar_one_or_none()
    if not meeting:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    check_group_access(current_user, meeting.shg_id)

    res = await get_meeting_collection_sheet(db, meeting_id, meeting.shg_id)

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Meeting Collection Sheet", str(res.meeting_id), str(res.meeting_date)])
        writer.writerow([])
        writer.writerow(["Member Name", "Savings Due", "EMI Due", "Arrears", "Fines", "Total Due"])
        for m in res.members:
            writer.writerow([
                m.member_name,
                str(m.savings_due),
                str(m.emi_due),
                str(m.arrears),
                str(m.fines_due),
                str(m.total_due),
            ])
        writer.writerow([])
        writer.writerow([
            "TOTALS",
            str(res.totals.total_savings_due),
            str(res.totals.total_emi_due),
            str(res.totals.total_arrears),
            str(res.totals.total_fines_due),
            str(res.totals.total_due),
        ])
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="collection_sheet_{meeting_id}.csv"'},
        )

    return res.model_dump()
