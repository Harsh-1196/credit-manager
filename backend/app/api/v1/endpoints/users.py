import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.core.security import hash_password
from app.db.models.auth import RefreshToken, User, UserGroupAccess, UserRole
from app.db.models.shg import SHG
from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.user import (
    UserCreateRequest,
    UserDetailResponse,
    UserGroupAccessItem,
    UserSummaryResponse,
    UserUpdateRequest,
)

router = APIRouter()


async def get_user_detail_by_id(user_id: uuid.UUID, db: AsyncSession) -> UserDetailResponse:
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise AppError(
            code="USER_NOT_FOUND",
            message="User not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    g_stmt = (
        select(UserGroupAccess, SHG.name)
        .outerjoin(SHG, UserGroupAccess.group_id == SHG.id)
        .where(UserGroupAccess.user_id == user.id)
    )
    g_res = await db.execute(g_stmt)
    group_items = [
        UserGroupAccessItem(
            group_id=access.group_id,
            group_name=group_name,
            access_level=access.access_level,
        )
        for access, group_name in g_res.all()
    ]

    return UserDetailResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        role=user.role,
        is_active=user.is_active,
        failed_login_count=user.failed_login_count,
        locked_until=user.locked_until,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
        group_access=group_items,
    )


@router.get("", response_model=PaginatedResponse[UserSummaryResponse])
async def list_users(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    role: UserRole | None = None,
) -> PaginatedResponse[UserSummaryResponse]:
    query = select(User)
    if role:
        query = query.where(User.role == role)

    total_stmt = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    items_stmt = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    items = list((await db.execute(items_stmt)).scalars().all())

    return PaginatedResponse[UserSummaryResponse](
        items=[
            UserSummaryResponse(
                id=u.id,
                email=u.email,
                phone=u.phone,
                role=u.role,
                is_active=u.is_active,
            )
            for u in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> UserDetailResponse:
    email = payload.email.lower().strip()

    # Check for existing email
    exists_stmt = select(User).where(User.email == email)
    if (await db.execute(exists_stmt)).scalar_one_or_none():
        raise AppError(
            code="USER_EMAIL_EXISTS",
            message="A user with this email address already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )

    user = User(
        email=email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Add group assignments if provided
    for gid in payload.group_ids:
        access = UserGroupAccess(
            user_id=user.id,
            group_id=gid,
            access_level="STANDARD",
        )
        db.add(access)

    await db.commit()

    await record_audit_log(
        db=db,
        action="USER_CREATED",
        entity_type="users",
        entity_id=user.id,
        after={"email": user.email, "role": user.role.value},
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return await get_user_detail_by_id(user.id, db)


@router.get("/{id}", response_model=UserDetailResponse)
async def get_user(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserDetailResponse:
    return await get_user_detail_by_id(id, db)


@router.patch("/{id}", response_model=UserDetailResponse)
async def update_user(
    id: uuid.UUID,
    payload: UserUpdateRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> UserDetailResponse:
    stmt = select(User).where(User.id == id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise AppError(
            code="USER_NOT_FOUND",
            message="User not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    before_data = {"phone": user.phone, "role": user.role.value, "is_active": user.is_active}

    if payload.phone is not None:
        user.phone = payload.phone
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    if payload.group_ids is not None:
        # Delete existing access
        del_stmt = select(UserGroupAccess).where(UserGroupAccess.user_id == user.id)
        existing_acc = list((await db.execute(del_stmt)).scalars().all())
        for acc in existing_acc:
            await db.delete(acc)

        for gid in payload.group_ids:
            new_acc = UserGroupAccess(
                user_id=user.id,
                group_id=gid,
                access_level="STANDARD",
            )
            db.add(new_acc)

    await db.commit()

    after_data = {"phone": user.phone, "role": user.role.value, "is_active": user.is_active}
    await record_audit_log(
        db=db,
        action="USER_UPDATED",
        entity_type="users",
        entity_id=user.id,
        before=before_data,
        after=after_data,
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return await get_user_detail_by_id(user.id, db)


@router.post("/{id}/deactivate", response_model=UserDetailResponse)
async def deactivate_user(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> UserDetailResponse:
    stmt = select(User).where(User.id == id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise AppError(
            code="USER_NOT_FOUND",
            message="User not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    user.is_active = False

    # Revoke all refresh tokens
    del_tokens_stmt = select(RefreshToken).where(RefreshToken.user_id == user.id)
    tokens = list((await db.execute(del_tokens_stmt)).scalars().all())
    for t in tokens:
        await db.delete(t)

    await db.commit()

    await record_audit_log(
        db=db,
        action="USER_DEACTIVATED",
        entity_type="users",
        entity_id=user.id,
        after={"is_active": False},
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return await get_user_detail_by_id(user.id, db)
