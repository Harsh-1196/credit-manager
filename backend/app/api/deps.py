import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.models.auth import User, UserGroupAccess, UserRole
from app.db.models.shg import Member
from app.db.session import get_db

security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate the currently authenticated user from Bearer token."""
    if not credentials or not credentials.credentials:
        raise AppError(
            code="UNAUTHORIZED",
            message="Authentication credentials were not provided.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    payload = decode_access_token(credentials.credentials)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AppError(
            code="INVALID_TOKEN",
            message="Token payload is missing subject.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as err:
        raise AppError(
            code="INVALID_TOKEN",
            message="Invalid user ID format in token.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from err

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise AppError(
            code="USER_NOT_FOUND",
            message="User account associated with this token no longer exists.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        raise AppError(
            code="ACCOUNT_INACTIVE",
            message="User account has been deactivated.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Attach user to request state for audit middleware
    request.state.user = user
    return user


def require_role(*allowed_roles: UserRole) -> Callable[..., Any]:
    """Dependency factory restricting access to specified roles."""

    async def role_checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise AppError(
                code="FORBIDDEN",
                message="You do not have permission to perform this action.",
                status_code=status.HTTP_403_FORBIDDEN,
                details={"required_roles": [r.value for r in allowed_roles], "your_role": current_user.role.value},
            )
        return current_user

    return role_checker


async def check_user_has_group_access(user: User, group_id: uuid.UUID, db: AsyncSession) -> bool:
    """Helper to verify if a user has access to a specific group."""
    if user.role == UserRole.ADMIN:
        return True

    if user.role in {UserRole.GROUP_LEADER, UserRole.AUDITOR}:
        stmt = select(UserGroupAccess).where(
            UserGroupAccess.user_id == user.id,
            UserGroupAccess.group_id == group_id,
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none() is not None

    if user.role == UserRole.MEMBER:
        member_stmt = select(Member).where(
            Member.user_id == user.id,
            Member.shg_id == group_id,
            Member.deleted_at.is_(None),
        )
        member_res = await db.execute(member_stmt)
        return member_res.scalar_one_or_none() is not None

    return False


def require_group_access(group_id_param: str = "id") -> Callable[..., Any]:
    """
    Object-level authorization dependency: ensures caller has permission for the specified group.
    Returns 404 (Not Found) if out of scope to avoid leaking existence (SPEC Section 2).
    """

    async def group_checker(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> tuple[User, uuid.UUID]:
        raw_id = request.path_params.get(group_id_param)
        if not raw_id:
            raise AppError(
                code="NOT_FOUND",
                message="Resource not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            group_id = uuid.UUID(str(raw_id))
        except ValueError as err:
            raise AppError(
                code="NOT_FOUND",
                message="Resource not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            ) from err

        has_access = await check_user_has_group_access(current_user, group_id, db)
        if not has_access:
            # SPEC rule: Return 404 (not 403) for objects outside the caller's scope
            raise AppError(
                code="NOT_FOUND",
                message="Group not found or inaccessible.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return current_user, group_id

    return group_checker
