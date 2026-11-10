import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import check_user_has_group_access, get_current_user
from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.core.security import mask_address, mask_phone
from app.db.models.auth import User, UserRole
from app.db.models.shg import SHG, Member, MemberRole, MemberStatus
from app.db.session import get_db
from app.domain.ledger.accounts import get_or_create_member_sub_accounts
from app.domain.savings.service import get_member_savings_balance, withdraw_member_savings
from app.schemas.common import PaginatedResponse
from app.schemas.member import (
    MemberCreateRequest,
    MemberExitRequest,
    MemberResponse,
    MemberUpdateRequest,
)

router = APIRouter()


def sanitize_id_proof(id_proof_number: str | None) -> str | None:
    """Extract and store strictly only the last 4 digits of any ID proof."""
    if not id_proof_number:
        return None
    cleaned = id_proof_number.strip().replace(" ", "").replace("-", "")
    return cleaned[-4:] if len(cleaned) >= 4 else cleaned


def format_member_response(member: Member, viewer: User) -> MemberResponse:
    """Format Member model to response with role-aware PII masking."""
    # Determine whether phone & address should be masked for this viewer
    # ADMIN and assigned GROUP_LEADER can view operational PII
    # AUDITOR and general MEMBERS (except self) receive masked PII per SPEC Section 9
    is_privileged = viewer.role in {UserRole.ADMIN, UserRole.GROUP_LEADER}
    is_self = member.user_id is not None and member.user_id == viewer.id

    phone = member.phone
    address = member.address

    if not is_privileged and not is_self:
        phone = mask_phone(member.phone)
        address = mask_address(member.address)

    roles = [r.role.value for r in member.roles if r.to_date is None]

    return MemberResponse(
        id=member.id,
        shg_id=member.shg_id,
        user_id=member.user_id,
        full_name=member.full_name,
        phone=phone,
        address=address,
        id_proof_type=member.id_proof_type,
        id_proof_last4=member.id_proof_last4,
        date_of_birth=member.date_of_birth,
        joined_on=member.joined_on,
        exited_on=member.exited_on,
        status=member.status,
        roles=roles,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


# 1. Group-scoped member list
@router.get("/groups/{group_id}/members", response_model=PaginatedResponse[MemberResponse])
async def list_group_members(
    group_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status_filter: MemberStatus | None = None,
    search: str | None = None,
) -> PaginatedResponse[MemberResponse]:
    has_access = await check_user_has_group_access(current_user, group_id, db)
    if not has_access:
        raise AppError(
            code="NOT_FOUND",
            message="Group not found or inaccessible.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    query = (
        select(Member).options(selectinload(Member.roles)).where(Member.shg_id == group_id, Member.deleted_at.is_(None))
    )

    if status_filter:
        query = query.where(Member.status == status_filter)

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Member.full_name.ilike(search_pattern),
                Member.phone.ilike(search_pattern),
            )
        )

    total_stmt = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    items_stmt = query.order_by(Member.full_name.asc()).offset(offset).limit(page_size)
    members = list((await db.execute(items_stmt)).scalars().all())

    return PaginatedResponse[MemberResponse](
        items=[format_member_response(m, current_user) for m in members],
        total=total,
        page=page,
        page_size=page_size,
    )


# 2. Add member to group
@router.post("/groups/{group_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def create_group_member(
    group_id: uuid.UUID,
    payload: MemberCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> MemberResponse:
    has_access = await check_user_has_group_access(current_user, group_id, db)
    if not has_access:
        raise AppError(
            code="NOT_FOUND",
            message="Group not found or inaccessible.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(
            code="FORBIDDEN",
            message="Only Administrators and Group Leaders may enroll new members.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Check that group exists and is active
    g_stmt = select(SHG).where(SHG.id == group_id)
    group = (await db.execute(g_stmt)).scalar_one_or_none()
    if not group:
        raise AppError(
            code="NOT_FOUND",
            message="Group not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    id_proof_last4 = sanitize_id_proof(payload.id_proof_number)

    member = Member(
        shg_id=group_id,
        user_id=payload.user_id,
        full_name=payload.full_name,
        phone=payload.phone,
        address=payload.address,
        id_proof_type=payload.id_proof_type,
        id_proof_last4=id_proof_last4,
        date_of_birth=payload.date_of_birth,
        joined_on=payload.joined_on,
        status=MemberStatus.ACTIVE,
    )
    db.add(member)
    await db.flush()

    # Assign initial role
    member_role = MemberRole(
        member_id=member.id,
        role=payload.role,
        from_date=payload.joined_on,
    )
    db.add(member_role)
    await db.flush()

    # Auto-create member sub-accounts (savings 2000-sub and loans 1100-sub)
    await get_or_create_member_sub_accounts(db, group_id, member)
    await db.commit()

    await record_audit_log(
        db=db,
        action="MEMBER_ENROLLED",
        entity_type="members",
        entity_id=member.id,
        after={"full_name": member.full_name, "shg_id": str(group_id), "role": payload.role.value},
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    # Re-fetch with roles eager loaded
    m_res = await db.execute(select(Member).options(selectinload(Member.roles)).where(Member.id == member.id))
    saved_member = m_res.scalar_one()
    return format_member_response(saved_member, current_user)


# 3. Get single member by ID
@router.get("/members/{id}", response_model=MemberResponse)
async def get_member(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberResponse:
    stmt = select(Member).options(selectinload(Member.roles)).where(Member.id == id, Member.deleted_at.is_(None))
    res = await db.execute(stmt)
    member = res.scalar_one_or_none()

    if not member:
        raise AppError(
            code="NOT_FOUND",
            message="Member not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Scoped authorization check: user must have access to member's SHG
    has_access = await check_user_has_group_access(current_user, member.shg_id, db)
    if not has_access:
        # SPEC rule: out of scope returns 404 (not 403)
        raise AppError(
            code="NOT_FOUND",
            message="Member not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return format_member_response(member, current_user)


# 4. Update member details
@router.patch("/members/{id}", response_model=MemberResponse)
async def update_member(
    id: uuid.UUID,
    payload: MemberUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> MemberResponse:
    stmt = select(Member).options(selectinload(Member.roles)).where(Member.id == id, Member.deleted_at.is_(None))
    res = await db.execute(stmt)
    member = res.scalar_one_or_none()

    if not member:
        raise AppError(
            code="NOT_FOUND",
            message="Member not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    has_access = await check_user_has_group_access(current_user, member.shg_id, db)
    if not has_access:
        raise AppError(
            code="NOT_FOUND",
            message="Member not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Only ADMIN or assigned GROUP_LEADER can update member profile
    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(
            code="FORBIDDEN",
            message="Only Administrators and Group Leaders may update member profiles.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    before = {"full_name": member.full_name, "phone": member.phone, "address": member.address}

    if payload.full_name is not None:
        member.full_name = payload.full_name
    if payload.phone is not None:
        member.phone = payload.phone
    if payload.address is not None:
        member.address = payload.address
    if payload.id_proof_type is not None:
        member.id_proof_type = payload.id_proof_type
    if payload.id_proof_number is not None:
        member.id_proof_last4 = sanitize_id_proof(payload.id_proof_number)
    if payload.date_of_birth is not None:
        member.date_of_birth = payload.date_of_birth

    if payload.role is not None:
        # Close old active role and insert new role
        for r in member.roles:
            if r.to_date is None:
                r.to_date = member.joined_on
        new_role = MemberRole(
            member_id=member.id,
            role=payload.role,
            from_date=member.joined_on,
        )
        db.add(new_role)

    await db.commit()

    after = {"full_name": member.full_name, "phone": member.phone, "address": member.address}
    await record_audit_log(
        db=db,
        action="MEMBER_UPDATED",
        entity_type="members",
        entity_id=member.id,
        before=before,
        after=after,
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return format_member_response(member, current_user)


# 5. Member exit
@router.post("/members/{id}/exit", response_model=MemberResponse)
async def exit_member(
    id: uuid.UUID,
    payload: MemberExitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> MemberResponse:
    stmt = select(Member).options(selectinload(Member.roles)).where(Member.id == id, Member.deleted_at.is_(None))
    res = await db.execute(stmt)
    member = res.scalar_one_or_none()

    if not member:
        raise AppError(
            code="NOT_FOUND",
            message="Member not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    has_access = await check_user_has_group_access(current_user, member.shg_id, db)
    if not has_access:
        raise AppError(
            code="NOT_FOUND",
            message="Member not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(
            code="FORBIDDEN",
            message="Only Administrators and Group Leaders may record a member exit.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Settle remaining savings via withdrawal entry per SPEC Section 7
    current_savings = await get_member_savings_balance(db, member.shg_id, member.id)
    if current_savings > 0:
        await withdraw_member_savings(
            db=db,
            shg_id=member.shg_id,
            member_id=member.id,
            amount=current_savings,
            posted_by=current_user.id,
            reason=f"Member exit settlement ({payload.reason or 'Exit'})",
            entry_date=payload.exited_on,
        )

    member.status = MemberStatus.EXITED
    member.exited_on = payload.exited_on

    await db.commit()

    await record_audit_log(
        db=db,
        action="MEMBER_EXIT",
        entity_type="members",
        entity_id=member.id,
        after={"status": MemberStatus.EXITED.value, "exited_on": str(payload.exited_on), "reason": payload.reason},
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return format_member_response(member, current_user)
