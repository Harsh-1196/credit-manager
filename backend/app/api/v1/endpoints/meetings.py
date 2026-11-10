import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import check_user_has_group_access, get_current_user, require_group_access
from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.core.idempotency import check_idempotency, compute_request_hash, save_idempotency_record
from app.core.money import money_to_str, quantize_money
from app.db.models.auth import User, UserRole
from app.db.models.ledger import JournalSourceType
from app.db.models.meetings import Attendance, Meeting, MeetingStatus
from app.db.models.savings import SavingsDue, SavingsDueStatus
from app.db.models.shg import Member
from app.db.session import get_db
from app.domain.ledger.accounts import get_account_by_code, get_or_create_member_sub_accounts
from app.domain.ledger.posting import PostingLineDTO, post_journal_entry
from app.schemas.meetings import (
    AttendanceRecord,
    AttendanceUpdateRequest,
    MeetingBatchCollectionsRequest,
    MeetingBatchCollectionsResponse,
    MeetingCreateRequest,
    MeetingDetailResponse,
    MeetingResponse,
    MeetingUpdateRequest,
)

router = APIRouter(tags=["meetings"])


@router.get("/groups/{id}/meetings", response_model=list[MeetingResponse])
async def list_group_meetings(
    id: uuid.UUID,
    group_scope: Annotated[tuple[User, uuid.UUID], Depends(require_group_access("id"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[MeetingResponse]:
    """
    Lists meetings for a given self-help group.
    """
    _, shg_id = group_scope

    stmt = (
        select(Meeting, func.count(Attendance.id).label("att_count"))
        .outerjoin(Attendance, Meeting.id == Attendance.meeting_id)
        .where(Meeting.shg_id == shg_id)
        .group_by(Meeting.id)
        .order_by(Meeting.meeting_date.desc(), Meeting.created_at.desc())
    )
    res = await db.execute(stmt)
    rows = res.all()

    return [
        MeetingResponse(
            id=m.id,
            shg_id=m.shg_id,
            meeting_date=m.meeting_date,
            status=m.status,
            agenda=m.agenda,
            minutes=m.minutes,
            recorded_by=m.recorded_by,
            attendance_count=att_count,
        )
        for m, att_count in rows
    ]


@router.post("/groups/{id}/meetings", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def schedule_meeting(
    id: uuid.UUID,
    payload: MeetingCreateRequest,
    group_scope: Annotated[tuple[User, uuid.UUID], Depends(require_group_access("id"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> MeetingResponse:
    """
    Schedules a new SHG meeting.
    """
    current_user, shg_id = group_scope

    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(
            code="FORBIDDEN",
            message="Only leaders and administrators can schedule group meetings.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    meeting = Meeting(
        shg_id=shg_id,
        meeting_date=payload.meeting_date,
        agenda=payload.agenda,
        status=MeetingStatus.SCHEDULED,
        recorded_by=current_user.id,
    )
    db.add(meeting)
    await db.commit()

    await record_audit_log(
        db=db,
        action="MEETING_SCHEDULED",
        entity_type="meetings",
        entity_id=meeting.id,
        after={"meeting_date": str(meeting.meeting_date), "shg_id": str(shg_id)},
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return MeetingResponse(
        id=meeting.id,
        shg_id=meeting.shg_id,
        meeting_date=meeting.meeting_date,
        status=meeting.status,
        agenda=meeting.agenda,
        minutes=meeting.minutes,
        recorded_by=meeting.recorded_by,
        attendance_count=0,
    )


@router.get("/meetings/{id}", response_model=MeetingDetailResponse)
async def get_meeting_detail(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeetingDetailResponse:
    """
    Returns meeting details including attendance registers.
    """
    stmt = select(Meeting).options(selectinload(Meeting.attendance_records)).where(Meeting.id == id)
    res = await db.execute(stmt)
    meeting = res.scalar_one_or_none()

    if not meeting:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, meeting.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    att_list = [AttendanceRecord(member_id=a.member_id, status=a.status) for a in meeting.attendance_records]

    return MeetingDetailResponse(
        id=meeting.id,
        shg_id=meeting.shg_id,
        meeting_date=meeting.meeting_date,
        status=meeting.status,
        agenda=meeting.agenda,
        minutes=meeting.minutes,
        recorded_by=meeting.recorded_by,
        attendance_count=len(att_list),
        attendance=att_list,
    )


@router.patch("/meetings/{id}", response_model=MeetingResponse)
async def update_meeting(
    id: uuid.UUID,
    payload: MeetingUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> MeetingResponse:
    """
    Updates meeting status, agenda, or minute book.
    """
    stmt = select(Meeting).where(Meeting.id == id)
    res = await db.execute(stmt)
    meeting = res.scalar_one_or_none()

    if not meeting:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, meeting.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(code="FORBIDDEN", message="Permission denied.", status_code=status.HTTP_403_FORBIDDEN)

    before = {"status": meeting.status.value, "agenda": meeting.agenda, "minutes": meeting.minutes}

    if payload.status is not None:
        meeting.status = payload.status
    if payload.agenda is not None:
        meeting.agenda = payload.agenda
    if payload.minutes is not None:
        meeting.minutes = payload.minutes

    await db.commit()

    after = {"status": meeting.status.value, "agenda": meeting.agenda, "minutes": meeting.minutes}
    await record_audit_log(
        db=db,
        action="MEETING_UPDATED",
        entity_type="meetings",
        entity_id=meeting.id,
        before=before,
        after=after,
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return MeetingResponse(
        id=meeting.id,
        shg_id=meeting.shg_id,
        meeting_date=meeting.meeting_date,
        status=meeting.status,
        agenda=meeting.agenda,
        minutes=meeting.minutes,
        recorded_by=meeting.recorded_by,
        attendance_count=0,
    )


@router.put("/meetings/{id}/attendance", response_model=MeetingDetailResponse)
async def update_meeting_attendance(
    id: uuid.UUID,
    payload: AttendanceUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> MeetingDetailResponse:
    """
    Bulk records member attendance for a meeting.
    """
    stmt = select(Meeting).options(selectinload(Meeting.attendance_records)).where(Meeting.id == id)
    res = await db.execute(stmt)
    meeting = res.scalar_one_or_none()

    if not meeting:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, meeting.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(code="FORBIDDEN", message="Permission denied.", status_code=status.HTTP_403_FORBIDDEN)

    # Delete existing attendance for this meeting
    existing_stmt = select(Attendance).where(Attendance.meeting_id == id)
    existing_res = await db.execute(existing_stmt)
    for att in existing_res.scalars().all():
        await db.delete(att)
    await db.flush()

    for item in payload.attendance:
        att = Attendance(
            meeting_id=meeting.id,
            member_id=item.member_id,
            status=item.status,
        )
        db.add(att)

    await db.commit()

    return await get_meeting_detail(id=meeting.id, current_user=current_user, db=db)


@router.post("/meetings/{id}/collections", response_model=MeetingBatchCollectionsResponse)
async def batch_meeting_collections(
    id: uuid.UUID,
    payload: MeetingBatchCollectionsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response | MeetingBatchCollectionsResponse:
    """
    SPEC 4.3 & 8: Batch endpoint to record savings and fines for many members at once.
    Posts a single balanced, atomic journal entry and updates member savings dues idempotently.
    """
    idem_key = idempotency_key_header or payload.idempotency_key

    stmt = select(Meeting).where(Meeting.id == id)
    res = await db.execute(stmt)
    meeting = res.scalar_one_or_none()

    if not meeting:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, meeting.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    if current_user.role not in {UserRole.ADMIN, UserRole.GROUP_LEADER}:
        raise AppError(code="FORBIDDEN", message="Permission denied.", status_code=status.HTTP_403_FORBIDDEN)

    scope = f"meeting_batch:{meeting.id}"
    req_hash = compute_request_hash(payload.model_dump(mode="json"))

    if idem_key:
        cached = await check_idempotency(db, key=idem_key, scope=scope, request_hash=req_hash)
        if cached:
            return Response(
                content=cached.response_body, status_code=cached.response_status, media_type="application/json"
            )

    # Fetch cash account (1000) and fine income account (4010)
    cash_account = await get_account_by_code(db, meeting.shg_id, "1000")
    fine_account = await get_account_by_code(db, meeting.shg_id, "4010")

    total_savings = Decimal("0.00")
    total_fines = Decimal("0.00")
    posting_lines: list[PostingLineDTO] = []
    processed_count = 0

    for item in payload.collections:
        s_amt = quantize_money(item.savings_amount)
        f_amt = quantize_money(item.fine_amount)

        if s_amt == Decimal("0.00") and f_amt == Decimal("0.00"):
            continue

        member_stmt = select(Member).where(Member.id == item.member_id, Member.shg_id == meeting.shg_id)
        m_res = await db.execute(member_stmt)
        member = m_res.scalar_one_or_none()
        if not member:
            continue

        savings_acc, _ = await get_or_create_member_sub_accounts(db, meeting.shg_id, member)

        if s_amt > Decimal("0.00"):
            total_savings += s_amt
            posting_lines.append(PostingLineDTO(account_id=savings_acc.id, debit=Decimal("0.00"), credit=s_amt))

            # Update savings dues
            due_stmt = select(SavingsDue).where(SavingsDue.member_id == member.id, SavingsDue.period == payload.period)
            due_res = await db.execute(due_stmt)
            due = due_res.scalar_one_or_none()
            if due:
                due.amount_paid = quantize_money(due.amount_paid + s_amt)
                if due.amount_paid >= due.amount_due:
                    due.status = SavingsDueStatus.PAID
                else:
                    due.status = SavingsDueStatus.PARTIAL

        if f_amt > Decimal("0.00"):
            total_fines += f_amt

        processed_count += 1

    total_collected = total_savings + total_fines

    if total_collected <= Decimal("0.00"):
        raise AppError(code="INVALID_AMOUNT", message="No non-zero collections to post.", status_code=400)

    # Debit Cash in Hand (1000) for entire batch
    posting_lines.insert(0, PostingLineDTO(account_id=cash_account.id, debit=total_collected, credit=Decimal("0.00")))

    # Credit Fine Income (4010) if any fines collected
    if total_fines > Decimal("0.00"):
        posting_lines.append(PostingLineDTO(account_id=fine_account.id, debit=Decimal("0.00"), credit=total_fines))

    # Post atomic journal entry
    entry = await post_journal_entry(
        db=db,
        shg_id=meeting.shg_id,
        entry_date=meeting.meeting_date,
        description=f"Batch meeting collections for {meeting.meeting_date} (Period {payload.period})",
        source_type=JournalSourceType.SAVINGS,
        lines=posting_lines,
        posted_by=current_user.id,
        source_id=meeting.id,
        idempotency_key=idem_key,
    )

    meeting.status = MeetingStatus.HELD
    await db.commit()

    resp_obj = MeetingBatchCollectionsResponse(
        total_collected=money_to_str(total_collected),
        members_count=processed_count,
        journal_entry_id=entry.id,
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
        action="MEETING_COLLECTIONS_POSTED",
        entity_type="meetings",
        entity_id=meeting.id,
        after={
            "total_collected": str(total_collected),
            "members_count": processed_count,
            "journal_entry_id": str(entry.id),
        },
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    request.state.audit_logged = True

    return resp_obj
