import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import check_user_has_group_access, get_current_user, require_role
from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.core.money import money_to_str, quantize_money
from app.db.models.auth import User, UserGroupAccess, UserRole
from app.db.models.shg import SHG, GroupSettings, Member, MemberStatus, SHGStatus
from app.db.session import get_db
from app.domain.ledger.accounts import initialize_shg_chart_of_accounts
from app.schemas.common import PaginatedResponse
from app.schemas.shg import (
    GroupSettingsResponse,
    GroupSettingsUpdateRequest,
    SHGCreateRequest,
    SHGResponse,
    SHGUpdateRequest,
)

router = APIRouter()


def format_group_settings(s: GroupSettings) -> GroupSettingsResponse:
    return GroupSettingsResponse(
        id=s.id,
        shg_id=s.shg_id,
        monthly_saving_amount=money_to_str(s.monthly_saving_amount),
        late_fine_per_day=money_to_str(s.late_fine_per_day),
        fine_grace_days=s.fine_grace_days,
        default_interest_rate=f"{s.default_interest_rate:.3f}",
        interest_type=s.interest_type,
        max_loan_multiple=f"{s.max_loan_multiple:.2f}",
        min_tenure_months=s.min_tenure_months,
        max_tenure_months=s.max_tenure_months,
        processing_fee_percent=f"{s.processing_fee_percent:.3f}",
        penalty_interest_rate=f"{s.penalty_interest_rate:.3f}",
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("", response_model=PaginatedResponse[SHGResponse])
async def list_groups(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: SHGStatus | None = None,
) -> PaginatedResponse[SHGResponse]:
    query = select(SHG).options(selectinload(SHG.settings))

    if status_filter:
        query = query.where(SHG.status == status_filter)

    # Scope filtering per SPEC Section 2
    if current_user.role == UserRole.ADMIN:
        pass  # Organization-wide access
    elif current_user.role in {UserRole.GROUP_LEADER, UserRole.AUDITOR}:
        allowed_subq = (
            select(UserGroupAccess.group_id).where(UserGroupAccess.user_id == current_user.id).scalar_subquery()
        )
        query = query.where(SHG.id.in_(allowed_subq))
    elif current_user.role == UserRole.MEMBER:
        member_subq = (
            select(Member.shg_id)
            .where(Member.user_id == current_user.id, Member.deleted_at.is_(None))
            .scalar_subquery()
        )
        query = query.where(SHG.id.in_(member_subq))
    else:
        return PaginatedResponse[SHGResponse](items=[], total=0, page=page, page_size=page_size)

    total_stmt = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    items_stmt = query.order_by(SHG.name.asc()).offset(offset).limit(page_size)
    groups = list((await db.execute(items_stmt)).scalars().all())

    # Get active member counts for each group
    group_ids = [g.id for g in groups]
    counts_map: dict[uuid.UUID, int] = {}
    if group_ids:
        count_stmt = (
            select(Member.shg_id, func.count(Member.id))
            .where(
                Member.shg_id.in_(group_ids),
                Member.status == MemberStatus.ACTIVE,
                Member.deleted_at.is_(None),
            )
            .group_by(Member.shg_id)
        )
        c_res = await db.execute(count_stmt)
        for gid, count in c_res.all():
            counts_map[gid] = count

    return PaginatedResponse[SHGResponse](
        items=[
            SHGResponse(
                id=g.id,
                name=g.name,
                village=g.village,
                ward=g.ward,
                district=g.district,
                formation_date=g.formation_date,
                meeting_day=g.meeting_day,
                meeting_frequency=g.meeting_frequency,
                bank_account_label=g.bank_account_label,
                status=g.status,
                created_at=g.created_at,
                updated_at=g.updated_at,
                member_count=counts_map.get(g.id, 0),
                settings=format_group_settings(g.settings) if g.settings else None,
            )
            for g in groups
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=SHGResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: SHGCreateRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> SHGResponse:
    group = SHG(
        name=payload.name,
        village=payload.village,
        ward=payload.ward,
        district=payload.district,
        formation_date=payload.formation_date,
        meeting_day=payload.meeting_day,
        meeting_frequency=payload.meeting_frequency,
        bank_account_label=payload.bank_account_label,
        status=SHGStatus.ACTIVE,
    )
    db.add(group)
    await db.flush()

    # Create 1:1 group settings
    s_payload = payload.settings or GroupSettingsUpdateRequest()
    settings = GroupSettings(
        shg_id=group.id,
        monthly_saving_amount=quantize_money(s_payload.monthly_saving_amount or "200.00"),
        late_fine_per_day=quantize_money(s_payload.late_fine_per_day or "5.00"),
        fine_grace_days=s_payload.fine_grace_days or 5,
        default_interest_rate=Decimal(s_payload.default_interest_rate or "12.000"),
        interest_type=s_payload.interest_type or GroupSettings.interest_type.default.arg,  # type: ignore[attr-defined]
        max_loan_multiple=Decimal(s_payload.max_loan_multiple or "3.00"),
        min_tenure_months=s_payload.min_tenure_months or 3,
        max_tenure_months=s_payload.max_tenure_months or 24,
        processing_fee_percent=Decimal(s_payload.processing_fee_percent or "1.000"),
        penalty_interest_rate=Decimal(s_payload.penalty_interest_rate or "2.000"),
    )
    db.add(settings)
    await db.flush()

    # Auto-create per-SHG chart of accounts from SPEC section 5
    await initialize_shg_chart_of_accounts(db, group.id)
    await db.commit()

    await record_audit_log(
        db=db,
        action="GROUP_CREATED",
        entity_type="shgs",
        entity_id=group.id,
        after={"name": group.name, "village": group.village},
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return SHGResponse(
        id=group.id,
        name=group.name,
        village=group.village,
        ward=group.ward,
        district=group.district,
        formation_date=group.formation_date,
        meeting_day=group.meeting_day,
        meeting_frequency=group.meeting_frequency,
        bank_account_label=group.bank_account_label,
        status=group.status,
        created_at=group.created_at,
        updated_at=group.updated_at,
        member_count=0,
        settings=format_group_settings(settings),
    )


@router.get("/{id}", response_model=SHGResponse)
async def get_group(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SHGResponse:
    # Check permissions (SPEC rule: out of scope returns 404)
    has_access = await check_user_has_group_access(current_user, id, db)
    if not has_access:
        raise AppError(
            code="NOT_FOUND",
            message="Group not found or inaccessible.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    stmt = select(SHG).options(selectinload(SHG.settings)).where(SHG.id == id)
    res = await db.execute(stmt)
    group = res.scalar_one_or_none()
    if not group:
        raise AppError(
            code="NOT_FOUND",
            message="Group not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Count active members
    c_stmt = select(func.count(Member.id)).where(
        Member.shg_id == id, Member.status == MemberStatus.ACTIVE, Member.deleted_at.is_(None)
    )
    member_count = (await db.execute(c_stmt)).scalar() or 0

    return SHGResponse(
        id=group.id,
        name=group.name,
        village=group.village,
        ward=group.ward,
        district=group.district,
        formation_date=group.formation_date,
        meeting_day=group.meeting_day,
        meeting_frequency=group.meeting_frequency,
        bank_account_label=group.bank_account_label,
        status=group.status,
        created_at=group.created_at,
        updated_at=group.updated_at,
        member_count=member_count,
        settings=format_group_settings(group.settings) if group.settings else None,
    )


@router.patch("/{id}", response_model=SHGResponse)
async def update_group(
    id: uuid.UUID,
    payload: SHGUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> SHGResponse:
    has_access = await check_user_has_group_access(current_user, id, db)
    if not has_access:
        raise AppError(
            code="NOT_FOUND",
            message="Group not found or inaccessible.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Permission check: ADMIN or GROUP_LEADER
    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(
            code="FORBIDDEN",
            message="Only Administrators and Group Leaders may update group metadata.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    stmt = select(SHG).options(selectinload(SHG.settings)).where(SHG.id == id)
    group = (await db.execute(stmt)).scalar_one_or_none()
    if not group:
        raise AppError(
            code="NOT_FOUND",
            message="Group not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    before = {"name": group.name, "village": group.village, "status": group.status.value}

    if payload.name is not None:
        group.name = payload.name
    if payload.village is not None:
        group.village = payload.village
    if payload.ward is not None:
        group.ward = payload.ward
    if payload.district is not None:
        group.district = payload.district
    if payload.meeting_day is not None:
        group.meeting_day = payload.meeting_day
    if payload.meeting_frequency is not None:
        group.meeting_frequency = payload.meeting_frequency
    if payload.bank_account_label is not None:
        group.bank_account_label = payload.bank_account_label
    if payload.status is not None:
        # Only ADMIN may change group status (e.g. to CLOSED)
        if current_user.role != UserRole.ADMIN:
            raise AppError(
                code="FORBIDDEN",
                message="Only Administrators can change group status.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        group.status = payload.status

    await db.commit()

    after = {"name": group.name, "village": group.village, "status": group.status.value}
    await record_audit_log(
        db=db,
        action="GROUP_UPDATED",
        entity_type="shgs",
        entity_id=group.id,
        before=before,
        after=after,
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    c_stmt = select(func.count(Member.id)).where(
        Member.shg_id == id, Member.status == MemberStatus.ACTIVE, Member.deleted_at.is_(None)
    )
    member_count = (await db.execute(c_stmt)).scalar() or 0

    return SHGResponse(
        id=group.id,
        name=group.name,
        village=group.village,
        ward=group.ward,
        district=group.district,
        formation_date=group.formation_date,
        meeting_day=group.meeting_day,
        meeting_frequency=group.meeting_frequency,
        bank_account_label=group.bank_account_label,
        status=group.status,
        created_at=group.created_at,
        updated_at=group.updated_at,
        member_count=member_count,
        settings=format_group_settings(group.settings) if group.settings else None,
    )


@router.get("/{id}/settings", response_model=GroupSettingsResponse)
async def get_group_settings(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GroupSettingsResponse:
    has_access = await check_user_has_group_access(current_user, id, db)
    if not has_access:
        raise AppError(
            code="NOT_FOUND",
            message="Group not found or inaccessible.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    stmt = select(GroupSettings).where(GroupSettings.shg_id == id)
    settings = (await db.execute(stmt)).scalar_one_or_none()
    if not settings:
        raise AppError(
            code="NOT_FOUND",
            message="Group settings not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return format_group_settings(settings)


@router.put("/{id}/settings", response_model=GroupSettingsResponse)
async def update_group_settings(
    id: uuid.UUID,
    payload: GroupSettingsUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> GroupSettingsResponse:
    has_access = await check_user_has_group_access(current_user, id, db)
    if not has_access:
        raise AppError(
            code="NOT_FOUND",
            message="Group not found or inaccessible.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(
            code="FORBIDDEN",
            message="Only Administrators and Group Leaders may update group settings.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    stmt = select(GroupSettings).where(GroupSettings.shg_id == id)
    settings = (await db.execute(stmt)).scalar_one_or_none()
    if not settings:
        raise AppError(
            code="NOT_FOUND",
            message="Group settings not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    before = {
        "monthly_saving_amount": str(settings.monthly_saving_amount),
        "interest_rate": str(settings.default_interest_rate),
    }

    if payload.monthly_saving_amount is not None:
        settings.monthly_saving_amount = quantize_money(payload.monthly_saving_amount)
    if payload.late_fine_per_day is not None:
        settings.late_fine_per_day = quantize_money(payload.late_fine_per_day)
    if payload.fine_grace_days is not None:
        settings.fine_grace_days = payload.fine_grace_days
    if payload.default_interest_rate is not None:
        settings.default_interest_rate = Decimal(payload.default_interest_rate)
    if payload.interest_type is not None:
        settings.interest_type = payload.interest_type
    if payload.max_loan_multiple is not None:
        settings.max_loan_multiple = Decimal(payload.max_loan_multiple)
    if payload.min_tenure_months is not None:
        settings.min_tenure_months = payload.min_tenure_months
    if payload.max_tenure_months is not None:
        settings.max_tenure_months = payload.max_tenure_months
    if payload.processing_fee_percent is not None:
        settings.processing_fee_percent = Decimal(payload.processing_fee_percent)
    if payload.penalty_interest_rate is not None:
        settings.penalty_interest_rate = Decimal(payload.penalty_interest_rate)

    await db.commit()

    after = {
        "monthly_saving_amount": str(settings.monthly_saving_amount),
        "interest_rate": str(settings.default_interest_rate),
    }
    await record_audit_log(
        db=db,
        action="GROUP_SETTINGS_UPDATED",
        entity_type="group_settings",
        entity_id=settings.id,
        before=before,
        after=after,
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return format_group_settings(settings)
