import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import check_user_has_group_access, get_current_user, require_group_access
from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.db.models.auth import User, UserRole
from app.db.models.meetings import Attendance, Meeting, MeetingStatus
from app.db.session import get_db
from app.schemas.meetings import (
    AttendanceRecord,
    AttendanceUpdateRequest,
    CollectionSheetResponse,
    MeetingBatchCollectionsRequest,
    MeetingBatchCollectionsResponse,
    MeetingCreateRequest,
    MeetingDetailResponse,
    MeetingResponse,
    MeetingUpdateRequest,
    MemberAttendanceResponse,
)
from app.services.meetings import (
    get_meeting_collection_sheet,
    get_member_attendance_history,
    record_meeting_batch_collections,
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


@router.get("/meetings/{id}/collection-sheet", response_model=CollectionSheetResponse)
async def get_collection_sheet(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectionSheetResponse:
    """
    SPEC Phase 4 & 11: Returns the full meeting collection sheet with per-member
    savings dues, EMI dues, arrears, fines, and grand totals.
    """
    stmt = select(Meeting).where(Meeting.id == id)
    res = await db.execute(stmt)
    meeting = res.scalar_one_or_none()

    if not meeting:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, meeting.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=status.HTTP_404_NOT_FOUND)

    return await get_meeting_collection_sheet(db=db, meeting_id=id, shg_id=meeting.shg_id)


@router.get("/reports/collection-sheet/{meeting_id}", response_model=CollectionSheetResponse)
async def get_reports_collection_sheet(
    meeting_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectionSheetResponse:
    """
    SPEC Section 8 & 11 reports route alias for collection sheet.
    """
    return await get_collection_sheet(id=meeting_id, current_user=current_user, db=db)


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
    SPEC 4.3, 8 & Phase 4: Batch endpoint to record savings, EMIs and fines for many members atomically and idempotently.
    - One journal entry per member per collection, each balanced.
    - All-or-nothing failure rule.
    - Row-level locking on active loans.
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

    response, is_cached = await record_meeting_batch_collections(
        db=db,
        meeting_id=id,
        shg_id=meeting.shg_id,
        payload=payload,
        current_user=current_user,
        request=request,
        idempotency_key=idem_key,
    )

    if is_cached:
        return Response(
            content=response.model_dump_json(),
            status_code=status.HTTP_200_OK,
            media_type="application/json",
        )

    return response


@router.get("/members/{id}/attendance", response_model=MemberAttendanceResponse)
async def get_member_attendance(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberAttendanceResponse:
    """
    Returns a member's attendance register across all SHG meetings.
    """
    from app.db.models.shg import Member
    m_stmt = select(Member).where(Member.id == id)
    m_res = await db.execute(m_stmt)
    member = m_res.scalar_one_or_none()

    if not member:
        raise AppError(code="NOT_FOUND", message="Member not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, member.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Member not found.", status_code=status.HTTP_404_NOT_FOUND)

    return await get_member_attendance_history(db=db, member_id=id, shg_id=member.shg_id)
