import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.audit.service import record_audit_log
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    generate_csrf_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models.auth import RefreshToken, User, UserGroupAccess
from app.db.models.shg import SHG, Member
from app.db.session import get_db
from app.schemas.auth import ChangePasswordRequest, LoginRequest, MessageResponse, RefreshRequest, TokenResponse
from app.schemas.user import UserDetailResponse, UserGroupAccessItem, UserSummaryResponse

router = APIRouter()

COOKIE_NAME = "shg_refresh_token"
CSRF_COOKIE_NAME = "shg_csrf_token"


async def assemble_user_detail(user: User, db: AsyncSession) -> UserDetailResponse:
    """Helper to populate UserDetailResponse with group access & member linkage."""
    stmt = (
        select(UserGroupAccess, SHG.name)
        .outerjoin(SHG, UserGroupAccess.group_id == SHG.id)
        .where(UserGroupAccess.user_id == user.id)
    )
    res = await db.execute(stmt)
    group_items = [
        UserGroupAccessItem(
            group_id=access.group_id,
            group_name=group_name,
            access_level=access.access_level,
        )
        for access, group_name in res.all()
    ]

    member_id: uuid.UUID | None = None
    member_shg_id: uuid.UUID | None = None
    m_stmt = select(Member).where(Member.user_id == user.id, Member.deleted_at.is_(None))
    m_res = await db.execute(m_stmt)
    member = m_res.scalar_one_or_none()
    if member:
        member_id = member.id
        member_shg_id = member.shg_id

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
        member_id=member_id,
        member_shg_id=member_shg_id,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    email = payload.email.lower().strip()
    now = datetime.now(UTC)

    stmt = select(User).where(User.email == email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        # Prevent timing attacks with dummy hash verification
        verify_password("dummy", "$argon2id$v=19$m=19456,t=2,p=1$c29tZXNhbHQ$WldKbmNtbHpZVEZsWldKbA")
        raise AppError(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # Check 15-minute account lockout
    if user.locked_until:
        locked_until_utc = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=UTC)
        if locked_until_utc > now:
            minutes_left = int((locked_until_utc - now).total_seconds() / 60) + 1
            raise AppError(
                code="ACCOUNT_LOCKED",
                message=f"Account is temporarily locked due to too many failed attempts. Try again in {minutes_left} minutes.",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                details={"locked_until": locked_until_utc.isoformat()},
            )

    if not user.is_active:
        raise AppError(
            code="ACCOUNT_INACTIVE",
            message="Account has been deactivated. Contact an administrator.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Verify password
    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = now + timedelta(minutes=15)
        await db.commit()

        # Audit failed login attempt
        await record_audit_log(
            db=db,
            action="LOGIN_FAILED",
            entity_type="users",
            entity_id=user.id,
            request=request,
            actor_id=user.id,
            actor_role=user.role.value,
            after={"failed_count": user.failed_login_count, "locked": user.locked_until is not None},
        )
        await db.commit()

        raise AppError(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # Reset failure tracking on success
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    # Issue access token
    access_token = create_access_token(subject=str(user.id), role=user.role.value)

    # Issue refresh token with a new token family
    raw_refresh = generate_refresh_token()
    token_hash = hash_token(raw_refresh)
    family_id = str(uuid.uuid4())
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_row = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=expires_at,
    )
    db.add(refresh_row)
    await db.commit()

    # Set httpOnly, Secure, SameSite=Strict cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_refresh,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
        path="/",
    )

    # Set double-submit CSRF cookie
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.headers["X-CSRF-Token"] = csrf_token

    # Record audit log
    await record_audit_log(
        db=db,
        action="LOGIN_SUCCESS",
        entity_type="users",
        entity_id=user.id,
        request=request,
        actor_id=user.id,
        actor_role=user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserSummaryResponse(
            id=user.id,
            email=user.email,
            phone=user.phone,
            role=user.role,
            is_active=user.is_active,
        ),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    cookie_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    now = datetime.now(UTC)
    raw_token = cookie_token or (payload.refresh_token if payload else None)

    if not raw_token:
        raise AppError(
            code="UNAUTHORIZED",
            message="No refresh token provided.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token_hash = hash_token(raw_token)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    res = await db.execute(stmt)
    token_row = res.scalar_one_or_none()

    if not token_row:
        raise AppError(
            code="INVALID_REFRESH_TOKEN",
            message="Refresh token is invalid.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # REUSE DETECTION (SPEC Section 9)
    # If the token has already been revoked or replaced, it represents a token theft or replay attack.
    # We revoke the entire family immediately!
    if token_row.revoked_at is not None or token_row.replaced_by is not None:
        await db.execute(
            update(RefreshToken).where(RefreshToken.family_id == token_row.family_id).values(revoked_at=now)
        )
        await db.commit()
        response.delete_cookie(COOKIE_NAME, path="/")
        response.delete_cookie(CSRF_COOKIE_NAME, path="/")

        await record_audit_log(
            db=db,
            action="SECURITY_REFRESH_REUSE_DETECTED",
            entity_type="refresh_tokens",
            entity_id=token_row.id,
            request=request,
            actor_id=token_row.user_id,
            after={"family_id": token_row.family_id, "action": "family_revoked"},
        )
        await db.commit()

        raise AppError(
            code="REFRESH_TOKEN_REUSE_DETECTED",
            message="Refresh token reuse detected. All sessions in this token family have been revoked for your security.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    expires_at_utc = token_row.expires_at if token_row.expires_at.tzinfo else token_row.expires_at.replace(tzinfo=UTC)
    if expires_at_utc < now:
        raise AppError(
            code="REFRESH_TOKEN_EXPIRED",
            message="Refresh token has expired. Please log in again.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # Fetch user
    u_stmt = select(User).where(User.id == token_row.user_id)
    u_res = await db.execute(u_stmt)
    user = u_res.scalar_one_or_none()
    if not user or not user.is_active:
        raise AppError(
            code="UNAUTHORIZED",
            message="User account inactive or not found.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # Rotate refresh token: generate new token in same family, mark old as replaced
    new_raw_token = generate_refresh_token()
    new_token_hash = hash_token(new_raw_token)

    token_row.replaced_by = new_token_hash
    token_row.revoked_at = now

    new_refresh_row = RefreshToken(
        user_id=user.id,
        token_hash=new_token_hash,
        family_id=token_row.family_id,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_refresh_row)
    await db.commit()

    # Issue new 15-minute access token
    new_access_token = create_access_token(subject=str(user.id), role=user.role.value)

    response.set_cookie(
        key=COOKIE_NAME,
        value=new_raw_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,  # type: ignore[arg-type]
        path="/",
    )

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserSummaryResponse(
            id=user.id,
            email=user.email,
            phone=user.phone,
            role=user.role,
            is_active=user.is_active,
        ),
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    cookie_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    now = datetime.now(UTC)
    if cookie_token:
        token_hash = hash_token(cookie_token)
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        res = await db.execute(stmt)
        token_row = res.scalar_one_or_none()
        if token_row:
            # Revoke entire token family
            await db.execute(
                update(RefreshToken).where(RefreshToken.family_id == token_row.family_id).values(revoked_at=now)
            )
            await db.commit()

            await record_audit_log(
                db=db,
                action="LOGOUT",
                entity_type="users",
                entity_id=token_row.user_id,
                request=request,
                actor_id=token_row.user_id,
            )
            await db.commit()

    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    request.state.audit_logged = True
    return MessageResponse(message="Successfully logged out.")


@router.get("/me", response_model=UserDetailResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserDetailResponse:
    return await assemble_user_detail(current_user, db)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,  # type: ignore[assignment]
) -> MessageResponse:
    now = datetime.now(UTC)

    if not verify_password(payload.current_password, current_user.password_hash):
        raise AppError(
            code="INVALID_CURRENT_PASSWORD",
            message="Current password is not correct.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    current_user.password_hash = hash_password(payload.new_password)

    # Revoke all active refresh tokens for this user on password change
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == current_user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.commit()

    await record_audit_log(
        db=db,
        action="CHANGE_PASSWORD",
        entity_type="users",
        entity_id=current_user.id,
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    if request:
        request.state.audit_logged = True

    return MessageResponse(message="Password successfully changed. Active sessions have been revoked.")
