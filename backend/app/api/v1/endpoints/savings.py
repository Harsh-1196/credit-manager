import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import check_user_has_group_access, get_current_user, require_group_access
from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.core.idempotency import check_idempotency, compute_request_hash, save_idempotency_record
from app.core.money import money_to_str
from app.db.models.auth import User, UserRole
from app.db.models.savings import SavingsDue
from app.db.models.shg import Member
from app.db.session import get_db
from app.domain.savings.service import (
    collect_member_savings,
    generate_savings_dues_for_period,
    get_member_savings_balance,
    withdraw_member_savings,
)
from app.schemas.savings import (
    SavingsCollectRequest,
    SavingsCollectResponse,
    SavingsDueGenerateRequest,
    SavingsDueResponse,
    SavingsWithdrawRequest,
    SavingsWithdrawResponse,
)

router = APIRouter(tags=["savings"])


@router.post("/groups/{id}/savings-dues/generate", response_model=list[SavingsDueResponse])
async def generate_dues_endpoint(
    id: uuid.UUID,
    payload: SavingsDueGenerateRequest,
    group_scope: Annotated[tuple[User, uuid.UUID], Depends(require_group_access("id"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> list[SavingsDueResponse]:
    """
    Generates a savings_dues record for each active member in the group for the given period.
    """
    current_user, shg_id = group_scope

    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(
            code="FORBIDDEN",
            message="Only group leaders and administrators can generate monthly savings dues.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    dues = await generate_savings_dues_for_period(db, shg_id, payload.period)
    await db.commit()

    # Fetch dues with member details
    stmt = (
        select(SavingsDue)
        .options(selectinload(SavingsDue.member))
        .where(SavingsDue.shg_id == shg_id, SavingsDue.period == payload.period)
    )
    res = await db.execute(stmt)
    all_dues = res.scalars().all()

    await record_audit_log(
        db=db,
        action="SAVINGS_DUES_GENERATED",
        entity_type="savings_dues",
        entity_id=shg_id,
        after={"period": payload.period, "count": len(dues)},
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return [
        SavingsDueResponse(
            id=d.id,
            shg_id=d.shg_id,
            member_id=d.member_id,
            period=d.period,
            amount_due=money_to_str(d.amount_due),
            amount_paid=money_to_str(d.amount_paid),
            status=d.status,
            member_name=d.member.full_name if d.member else None,
        )
        for d in all_dues
    ]


@router.get("/groups/{id}/savings-dues", response_model=list[SavingsDueResponse])
async def list_group_savings_dues(
    id: uuid.UUID,
    group_scope: Annotated[tuple[User, uuid.UUID], Depends(require_group_access("id"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
) -> list[SavingsDueResponse]:
    """
    Lists savings dues for a group, optionally filtered by period (YYYY-MM).
    """
    _, shg_id = group_scope

    stmt = (
        select(SavingsDue)
        .options(selectinload(SavingsDue.member))
        .where(SavingsDue.shg_id == shg_id)
        .order_by(SavingsDue.period.desc())
    )
    if period:
        stmt = stmt.where(SavingsDue.period == period)

    res = await db.execute(stmt)
    dues = res.scalars().all()

    return [
        SavingsDueResponse(
            id=d.id,
            shg_id=d.shg_id,
            member_id=d.member_id,
            period=d.period,
            amount_due=money_to_str(d.amount_due),
            amount_paid=money_to_str(d.amount_paid),
            status=d.status,
            member_name=d.member.full_name if d.member else None,
        )
        for d in dues
    ]


@router.get("/members/{id}/savings")
async def get_member_savings_summary(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    """
    Returns a member's total accumulated savings balance and active pending dues.
    """
    member_stmt = select(Member).where(Member.id == id, Member.deleted_at.is_(None))
    member_res = await db.execute(member_stmt)
    member = member_res.scalar_one_or_none()

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

    balance = await get_member_savings_balance(db, member.shg_id, member.id)

    dues_stmt = select(SavingsDue).where(SavingsDue.member_id == id).order_by(SavingsDue.period.desc())
    dues_res = await db.execute(dues_stmt)
    dues = dues_res.scalars().all()

    return {
        "member_id": str(member.id),
        "member_name": member.full_name,
        "shg_id": str(member.shg_id),
        "total_savings_balance": money_to_str(balance),
        "dues": [
            {
                "id": str(d.id),
                "period": d.period,
                "amount_due": money_to_str(d.amount_due),
                "amount_paid": money_to_str(d.amount_paid),
                "status": d.status.value,
            }
            for d in dues
        ],
    }


@router.post("/savings/collect", response_model=SavingsCollectResponse)
async def collect_savings_endpoint(
    payload: SavingsCollectRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response | SavingsCollectResponse:
    """
    Records collection of savings (+ optional fine) for a member.
    Enforces double-entry ledger posting, updates savings_dues, and handles idempotency.
    """
    idem_key = idempotency_key_header or payload.idempotency_key

    # Fetch member to determine SHG scope
    member_stmt = select(Member).where(Member.id == payload.member_id, Member.deleted_at.is_(None))
    member_res = await db.execute(member_stmt)
    member = member_res.scalar_one_or_none()

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
            message="Only leaders and administrators can collect member savings.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Idempotency check
    scope = f"savings_collect:{member.shg_id}"
    req_hash = compute_request_hash(payload.model_dump(mode="json"))

    if idem_key:
        cached_record = await check_idempotency(db, key=idem_key, scope=scope, request_hash=req_hash)
        if cached_record:
            return Response(
                content=cached_record.response_body,
                status_code=cached_record.response_status,
                media_type="application/json",
            )

    due, new_balance = await collect_member_savings(
        db=db,
        shg_id=member.shg_id,
        member_id=member.id,
        amount=payload.amount,
        period=payload.period,
        posted_by=current_user.id,
        fine_amount=payload.fine_amount,
        entry_date=payload.entry_date,
        idempotency_key=idem_key,
    )
    await db.commit()

    resp_obj = SavingsCollectResponse(
        due=SavingsDueResponse(
            id=due.id,
            shg_id=due.shg_id,
            member_id=due.member_id,
            period=due.period,
            amount_due=money_to_str(due.amount_due),
            amount_paid=money_to_str(due.amount_paid),
            status=due.status,
            member_name=member.full_name,
        ),
        new_savings_balance=money_to_str(new_balance),
        message=f"Successfully collected savings of ₹{payload.amount} for {member.full_name}.",
    )

    resp_json = resp_obj.model_dump_json()

    if idem_key:
        await save_idempotency_record(
            db=db,
            key=idem_key,
            scope=scope,
            request_hash=req_hash,
            response_status=200,
            response_body=resp_json,
        )
        await db.commit()

    await record_audit_log(
        db=db,
        action="SAVINGS_COLLECTED",
        entity_type="savings_dues",
        entity_id=due.id,
        after={
            "member_id": str(member.id),
            "amount": str(payload.amount),
            "fine": str(payload.fine_amount),
            "period": payload.period,
            "new_balance": str(new_balance),
        },
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return resp_obj


@router.post("/savings/withdraw", response_model=SavingsWithdrawResponse)
async def withdraw_savings_endpoint(
    payload: SavingsWithdrawRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response | SavingsWithdrawResponse:
    """
    Processes a savings withdrawal (e.g. member exit settlement).
    Enforces double-entry ledger posting and validates balance sufficiency.
    """
    idem_key = idempotency_key_header or payload.idempotency_key

    member_stmt = select(Member).where(Member.id == payload.member_id, Member.deleted_at.is_(None))
    member_res = await db.execute(member_stmt)
    member = member_res.scalar_one_or_none()

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
            message="Only leaders and administrators can authorize savings withdrawals.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    scope = f"savings_withdraw:{member.shg_id}"
    req_hash = compute_request_hash(payload.model_dump(mode="json"))

    if idem_key:
        cached_record = await check_idempotency(db, key=idem_key, scope=scope, request_hash=req_hash)
        if cached_record:
            return Response(
                content=cached_record.response_body,
                status_code=cached_record.response_status,
                media_type="application/json",
            )

    new_balance = await withdraw_member_savings(
        db=db,
        shg_id=member.shg_id,
        member_id=member.id,
        amount=payload.amount,
        posted_by=current_user.id,
        reason=payload.reason,
        entry_date=payload.entry_date,
        idempotency_key=idem_key,
    )
    await db.commit()

    resp_obj = SavingsWithdrawResponse(
        member_id=member.id,
        withdrawn_amount=money_to_str(payload.amount),
        new_savings_balance=money_to_str(new_balance),
        message=f"Successfully withdrew ₹{payload.amount} for {member.full_name}.",
    )

    resp_json = resp_obj.model_dump_json()

    if idem_key:
        await save_idempotency_record(
            db=db,
            key=idem_key,
            scope=scope,
            request_hash=req_hash,
            response_status=200,
            response_body=resp_json,
        )
        await db.commit()

    await record_audit_log(
        db=db,
        action="SAVINGS_WITHDRAWN",
        entity_type="members",
        entity_id=member.id,
        after={
            "member_id": str(member.id),
            "withdrawn_amount": str(payload.amount),
            "reason": payload.reason,
            "new_balance": str(new_balance),
        },
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return resp_obj
