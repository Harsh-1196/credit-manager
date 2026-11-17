from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.errors import AppError
from app.db.models.auth import User, UserRole
from app.db.models.shg import SHG, Member
from app.domain.reports.schemas import DashboardResponse
from app.domain.reports.service import generate_group_dashboard_report, generate_member_statement_report

router = APIRouter()


def check_group_access(user: User, shg_id: uuid.UUID) -> None:
    if user.role == UserRole.ADMIN:
        return
    permitted_ids = [ga.group_id for ga in (getattr(user, "group_access", None) or [])]
    if shg_id not in permitted_ids:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=status.HTTP_404_NOT_FOUND)


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    shg_id: uuid.UUID | None = Query(None, description="Target SHG UUID for leaders/admins"),
    as_of_date: date | None = Query(None, description="As of date for dashboard metrics"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    # 1. Member view: personal statement & dues
    if current_user.role == UserRole.MEMBER:
        stmt_mem = select(Member).where(Member.user_id == current_user.id)
        member = (await db.execute(stmt_mem)).scalar_one_or_none()
        if not member:
            raise AppError(
                code="MEMBER_PROFILE_NOT_FOUND",
                message="No member profile linked to this user account.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        member_rep = await generate_member_statement_report(db, member_id=member.id)
        return DashboardResponse(
            role="MEMBER",
            member_dashboard=member_rep,
        )

    # 2. Group Leader / Auditor / Admin view: group overview with trends
    target_shg_id = shg_id
    if not target_shg_id:
        if current_user.role == UserRole.ADMIN:
            stmt_first_shg = select(SHG.id).order_by(SHG.created_at.asc()).limit(1)
            target_shg_id = (await db.execute(stmt_first_shg)).scalar_one_or_none()
        elif current_user.group_access:
            target_shg_id = current_user.group_access[0].group_id

    if not target_shg_id:
        raise AppError(
            code="NO_GROUP_AVAILABLE",
            message="No Self-Help Group available for dashboard viewing.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    check_group_access(current_user, target_shg_id)

    group_rep = await generate_group_dashboard_report(
        db, shg_id=target_shg_id, as_of_date=as_of_date
    )
    return DashboardResponse(
        role=current_user.role.value,
        group_dashboard=group_rep,
    )
