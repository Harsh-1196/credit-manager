import uuid
from decimal import Decimal

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.core.idempotency import (
    check_idempotency,
    compute_request_hash,
    save_idempotency_record,
)
from app.core.money import money_to_str, quantize_money
from app.db.models.auth import User, UserRole
from app.db.models.ledger import JournalSourceType
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.meetings import Attendance, AttendanceStatus, Meeting, MeetingStatus
from app.db.models.savings import SavingsDue, SavingsDueStatus
from app.db.models.shg import SHG, GroupSettings, Member, MemberStatus
from app.domain.ledger.accounts import (
    get_account_by_code,
    get_or_create_member_sub_accounts,
)
from app.domain.ledger.posting import PostingLineDTO, post_journal_entry
from app.domain.loans.allocation import allocate_repayment
from app.domain.loans.state_machine import LoanStateMachine
from app.domain.meetings.collection_sheet import build_collection_sheet
from app.domain.outbox.service import create_outbox_event
from app.schemas.meetings import (
    CollectionSheetResponse,
    MeetingBatchCollectionsRequest,
    MeetingBatchCollectionsResponse,
    MemberAttendanceRecord,
    MemberAttendanceResponse,
    MemberAttendanceSummary,
)


async def get_meeting_collection_sheet(
    db: AsyncSession,
    meeting_id: uuid.UUID,
    shg_id: uuid.UUID,
) -> CollectionSheetResponse:
    """
    Assembles the complete collection sheet for a meeting per SPEC sections 8, 11, and 12.5.
    """
    # 1. Fetch meeting and SHG
    m_stmt = select(Meeting).where(Meeting.id == meeting_id, Meeting.shg_id == shg_id)
    m_res = await db.execute(m_stmt)
    meeting = m_res.scalar_one_or_none()
    if not meeting:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=404)

    shg_stmt = select(SHG).where(SHG.id == shg_id)
    shg_res = await db.execute(shg_stmt)
    shg = shg_res.scalar_one_or_none()
    if not shg:
        raise AppError(code="NOT_FOUND", message="Group not found.", status_code=404)

    # 2. Group settings
    settings_stmt = select(GroupSettings).where(GroupSettings.shg_id == shg_id)
    settings_res = await db.execute(settings_stmt)
    settings = settings_res.scalar_one_or_none()

    # 3. Active group members
    members_stmt = (
        select(Member)
        .where(Member.shg_id == shg_id, Member.status == MemberStatus.ACTIVE)
        .order_by(Member.full_name)
    )
    members_res = await db.execute(members_stmt)
    members = list(members_res.scalars().all())

    # 4. Existing attendance for this meeting
    att_stmt = select(Attendance).where(Attendance.meeting_id == meeting.id)
    att_res = await db.execute(att_stmt)
    attendance_map = {a.member_id: a.status for a in att_res.scalars().all()}

    # 5. Period savings dues
    period = meeting.meeting_date.strftime("%Y-%m")
    dues_stmt = select(SavingsDue).where(SavingsDue.shg_id == shg_id, SavingsDue.period == period)
    dues_res = await db.execute(dues_stmt)
    savings_dues_map = {d.member_id: d for d in dues_res.scalars().all()}

    # 6. Active and overdue loans for group members
    member_ids = [m.id for m in members]
    loans_stmt = (
        select(Loan)
        .options(selectinload(Loan.schedule))
        .where(
            Loan.shg_id == shg_id,
            Loan.member_id.in_(member_ids),
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]),
        )
    )
    loans_res = await db.execute(loans_stmt)
    active_loans_list = list(loans_res.scalars().all())
    # One active loan per member mapping (latest active/overdue)
    active_loans_map: dict[uuid.UUID, Loan] = {}
    for loan_obj in active_loans_list:
        if loan_obj.member_id not in active_loans_map:
            active_loans_map[loan_obj.member_id] = loan_obj

    return build_collection_sheet(
        meeting=meeting,
        shg=shg,
        settings=settings,
        members=members,
        attendance_map=attendance_map,
        savings_dues_map=savings_dues_map,
        active_loans_map=active_loans_map,
        period=period,
    )


async def record_meeting_batch_collections(
    db: AsyncSession,
    meeting_id: uuid.UUID,
    shg_id: uuid.UUID,
    payload: MeetingBatchCollectionsRequest,
    current_user: User,
    request: Request | None = None,
    idempotency_key: str | None = None,
) -> tuple[MeetingBatchCollectionsResponse, bool]:
    """
    SPEC Phase 4: Atomic, idempotent batch collection of savings, EMIs, and fines.
    Rules:
      - All-or-nothing failure rule: Any error rolls back all journal entries, dues, and attendance.
      - One journal entry per member per collection, each strictly balanced.
      - Concurrency safe: Takes pessimistic locks on affected loan and schedule rows.
      - Returns (response_dto, is_cached_replay).
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.GROUP_LEADER]:
        raise AppError(
            code="UNAUTHORIZED",
            message="Only GROUP_LEADER or ADMIN can record batch meeting collections.",
            status_code=403,
        )

    # 1. Fetch meeting
    m_stmt = select(Meeting).where(Meeting.id == meeting_id, Meeting.shg_id == shg_id)
    m_res = await db.execute(m_stmt)
    meeting = m_res.scalar_one_or_none()
    if not meeting:
        raise AppError(code="NOT_FOUND", message="Meeting not found.", status_code=404)

    # 2. Check Idempotency
    scope = f"meeting_batch:{meeting.id}"
    req_hash = compute_request_hash(payload.model_dump(mode="json"))
    idem_key = idempotency_key or payload.idempotency_key

    if idem_key:
        cached = await check_idempotency(db, key=idem_key, scope=scope, request_hash=req_hash)
        if cached:
            cached_resp = MeetingBatchCollectionsResponse.model_validate_json(cached.response_body)
            return cached_resp, True

    # 3. Determine Billing Period
    period = payload.period or meeting.meeting_date.strftime("%Y-%m")

    # 4. Fetch group settings
    settings_stmt = select(GroupSettings).where(GroupSettings.shg_id == shg_id)
    settings_res = await db.execute(settings_stmt)
    settings = settings_res.scalar_one_or_none()
    prepayment_policy = settings.prepayment_policy if settings else "REDUCE_TENURE"

    # 5. Pre-validate and fetch all participating members
    member_ids = [item.member_id for item in payload.collections]
    if not member_ids:
        raise AppError(code="INVALID_REQUEST", message="No member collections submitted.", status_code=400)

    members_stmt = select(Member).where(Member.id.in_(member_ids), Member.shg_id == shg_id)
    members_res = await db.execute(members_stmt)
    members_by_id = {m.id: m for m in members_res.scalars().all()}

    # All-or-nothing validation: Ensure every member exists in this SHG
    for item in payload.collections:
        if item.member_id not in members_by_id:
            raise AppError(
                code="MEMBER_NOT_FOUND",
                message=f"Member '{item.member_id}' does not belong to this group.",
                status_code=400,
            )
        if item.savings_amount < Decimal("0.00") or item.loan_repayment_amount < Decimal("0.00") or item.fine_amount < Decimal("0.00"):
            raise AppError(
                code="INVALID_AMOUNT",
                message="Collection amounts cannot be negative.",
                status_code=400,
            )

    # 6. Fetch chart of accounts
    cash_account = await get_account_by_code(db, shg_id, "1000")
    fine_account = await get_account_by_code(db, shg_id, "4010")
    interest_account = await get_account_by_code(db, shg_id, "4000")

    # 7. Check loans for members with loan repayments (with row-level lock)
    members_with_repayments = [
        item.member_id for item in payload.collections if quantize_money(item.loan_repayment_amount) > Decimal("0.00")
    ]
    loans_by_member: dict[uuid.UUID, Loan] = {}
    if members_with_repayments:
        loans_stmt = (
            select(Loan)
            .options(selectinload(Loan.schedule))
            .where(
                Loan.shg_id == shg_id,
                Loan.member_id.in_(members_with_repayments),
                Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]),
            )
            .with_for_update()
        )
        loans_res = await db.execute(loans_stmt)
        for loan_obj in loans_res.scalars().all():
            loans_by_member[loan_obj.member_id] = loan_obj

        # All-or-nothing check: Each member with loan repayment must have an active loan
        for mid in members_with_repayments:
            if mid not in loans_by_member:
                m_name = members_by_id[mid].full_name
                raise AppError(
                    code="NO_ACTIVE_LOAN",
                    message=f"Member '{m_name}' has no active loan to repay.",
                    status_code=400,
                )

    # 8. Fetch savings dues for the period
    dues_stmt = select(SavingsDue).where(SavingsDue.shg_id == shg_id, SavingsDue.period == period)
    dues_res = await db.execute(dues_stmt)
    dues_by_member = {d.member_id: d for d in dues_res.scalars().all()}

    # 9. Update Attendance
    # Delete existing attendance for this meeting and insert new status
    del_att = select(Attendance).where(Attendance.meeting_id == meeting.id)
    del_res = await db.execute(del_att)
    for old_att in del_res.scalars().all():
        await db.delete(old_att)
    await db.flush()

    for item in payload.collections:
        att = Attendance(
            meeting_id=meeting.id,
            member_id=item.member_id,
            status=item.attendance_status,
        )
        db.add(att)

    # 10. Process Collections & Post Balanced Per-Member Journal Entries
    total_savings = Decimal("0.00")
    total_repayments = Decimal("0.00")
    total_fines = Decimal("0.00")
    posted_entry_ids: list[uuid.UUID] = []
    contributing_members = 0

    for item in payload.collections:
        s_amt = quantize_money(item.savings_amount)
        r_amt = quantize_money(item.loan_repayment_amount)
        f_amt = quantize_money(item.fine_amount)
        member_total = quantize_money(s_amt + r_amt + f_amt)

        if member_total <= Decimal("0.00"):
            continue

        member = members_by_id[item.member_id]
        contributing_members += 1
        total_savings += s_amt
        total_repayments += r_amt
        total_fines += f_amt

        # Sub-accounts for this member
        savings_sub_acc, loans_sub_acc = await get_or_create_member_sub_accounts(db, shg_id, member)

        # Build balanced journal lines for this member
        journal_lines: list[PostingLineDTO] = [
            # Debit: Cash in Hand (1000) for total cash collected from this member
            PostingLineDTO(account_id=cash_account.id, debit=member_total, credit=Decimal("0.00")),
        ]

        # Savings credit
        if s_amt > Decimal("0.00"):
            journal_lines.append(
                PostingLineDTO(account_id=savings_sub_acc.id, debit=Decimal("0.00"), credit=s_amt)
            )
            # Update savings due
            due_obj = dues_by_member.get(member.id)
            if due_obj:
                due_obj.amount_paid = quantize_money(due_obj.amount_paid + s_amt)
                if due_obj.amount_paid >= due_obj.amount_due:
                    due_obj.status = SavingsDueStatus.PAID
                else:
                    due_obj.status = SavingsDueStatus.PARTIAL
            else:
                # Create savings due record if it didn't exist yet
                new_due = SavingsDue(
                    shg_id=shg_id,
                    member_id=member.id,
                    period=period,
                    amount_due=s_amt,
                    amount_paid=s_amt,
                    status=SavingsDueStatus.PAID,
                )
                db.add(new_due)

        # Loan repayment credit lines
        if r_amt > Decimal("0.00"):
            loan = loans_by_member[member.id]

            # Lock schedule items for this loan
            sched_stmt = (
                select(LoanSchedule)
                .where(LoanSchedule.loan_id == loan.id)
                .order_by(LoanSchedule.installment_no)
                .with_for_update()
            )
            sched_res = await db.execute(sched_stmt)
            schedule_items = list(sched_res.scalars().all())

            alloc_res = allocate_repayment(
                loan=loan,
                schedule_items=schedule_items,
                payment_amount=r_amt,
                as_of_date=meeting.meeting_date,
                prepayment_policy=prepayment_policy,
            )

            if alloc_res.total_principal > Decimal("0.00"):
                journal_lines.append(
                    PostingLineDTO(
                        account_id=loans_sub_acc.id,
                        debit=Decimal("0.00"),
                        credit=alloc_res.total_principal,
                    )
                )
            if alloc_res.total_interest > Decimal("0.00"):
                journal_lines.append(
                    PostingLineDTO(
                        account_id=interest_account.id,
                        debit=Decimal("0.00"),
                        credit=alloc_res.total_interest,
                    )
                )
            if alloc_res.total_penalty > Decimal("0.00"):
                journal_lines.append(
                    PostingLineDTO(
                        account_id=fine_account.id,
                        debit=Decimal("0.00"),
                        credit=alloc_res.total_penalty,
                    )
                )

            # Update loan status if fully paid or cured
            if alloc_res.is_loan_fully_paid:
                await LoanStateMachine.transition(
                    db=db,
                    loan=loan,
                    to_status=LoanStatus.CLOSED,
                    actor=current_user,
                    reason="Loan fully repaid during meeting collection",
                )
            elif loan.status == LoanStatus.OVERDUE:
                # Check if cured
                any_overdue = any(
                    s.status == LoanScheduleStatus.OVERDUE for s in schedule_items
                )
                if not any_overdue:
                    await LoanStateMachine.transition(
                        db=db,
                        loan=loan,
                        to_status=LoanStatus.ACTIVE,
                        actor=current_user,
                        reason="Overdue arrears cured during meeting collection",
                    )

        # Fine credit line
        if f_amt > Decimal("0.00"):
            journal_lines.append(
                PostingLineDTO(account_id=fine_account.id, debit=Decimal("0.00"), credit=f_amt)
            )

        # Post balanced entry for this member
        member_idem_key = f"{idem_key}:{member.id}" if idem_key else None
        entry = await post_journal_entry(
            db=db,
            shg_id=shg_id,
            entry_date=meeting.meeting_date,
            description=f"Meeting collection - {member.full_name} (Savings: ₹{s_amt}, EMI: ₹{r_amt}, Fine: ₹{f_amt})",
            source_type=JournalSourceType.SAVINGS,
            lines=journal_lines,
            posted_by=current_user.id,
            source_id=meeting.id,
            idempotency_key=member_idem_key,
        )
        posted_entry_ids.append(entry.id)

        # Record transactional outbox events
        if s_amt > Decimal("0.00") or f_amt > Decimal("0.00"):
            await create_outbox_event(
                db=db,
                event_type="SAVINGS_COLLECTED",
                aggregate_type="SAVINGS",
                aggregate_id=member.id,
                shg_id=shg_id,
                payload={
                    "member_id": str(member.id),
                    "amount": str(s_amt),
                    "fine_amount": str(f_amt),
                    "meeting_id": str(meeting.id),
                    "period": period,
                },
            )
        if r_amt > Decimal("0.00") and member.id in loans_by_member:
            m_loan = loans_by_member[member.id]
            await create_outbox_event(
                db=db,
                event_type="LOAN_REPAID",
                aggregate_type="LOAN",
                aggregate_id=m_loan.id,
                shg_id=shg_id,
                payload={
                    "loan_id": str(m_loan.id),
                    "member_id": str(member.id),
                    "amount": str(r_amt),
                    "meeting_id": str(meeting.id),
                },
            )

    # 11. Update meeting status and recorded_by
    meeting.status = MeetingStatus.HELD
    meeting.recorded_by = current_user.id
    await db.commit()

    total_grand = total_savings + total_repayments + total_fines
    response = MeetingBatchCollectionsResponse(
        total_collected=money_to_str(total_grand),
        total_savings=money_to_str(total_savings),
        total_loan_repayment=money_to_str(total_repayments),
        total_fines=money_to_str(total_fines),
        members_count=contributing_members,
        journal_entries_count=len(posted_entry_ids),
        journal_entry_ids=posted_entry_ids,
        meeting_status=meeting.status,
    )

    # 12. Save Idempotency Record
    if idem_key:
        await save_idempotency_record(
            db=db,
            key=idem_key,
            scope=scope,
            request_hash=req_hash,
            response_status=200,
            response_body=response.model_dump_json(),
        )
        await db.commit()

    # 13. Audit Log
    await record_audit_log(
        db=db,
        action="MEETING_COLLECTIONS_RECORDED",
        entity_type="meetings",
        entity_id=meeting.id,
        after={
            "total_collected": str(total_grand),
            "total_savings": str(total_savings),
            "total_repayments": str(total_repayments),
            "total_fines": str(total_fines),
            "journal_entries_count": len(posted_entry_ids),
        },
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )
    await db.commit()
    if request:
        request.state.audit_logged = True

    return response, False


async def get_member_attendance_history(
    db: AsyncSession,
    member_id: uuid.UUID,
    shg_id: uuid.UUID,
) -> MemberAttendanceResponse:
    """
    Returns a member's complete meeting attendance register and summary metrics.
    """
    m_stmt = select(Member).where(Member.id == member_id, Member.shg_id == shg_id)
    m_res = await db.execute(m_stmt)
    member = m_res.scalar_one_or_none()
    if not member:
        raise AppError(code="NOT_FOUND", message="Member not found.", status_code=404)

    stmt = (
        select(Attendance, Meeting)
        .join(Meeting, Attendance.meeting_id == Meeting.id)
        .where(Attendance.member_id == member_id)
        .order_by(Meeting.meeting_date.desc())
    )
    res = await db.execute(stmt)
    rows = res.all()

    records: list[MemberAttendanceRecord] = []
    present_cnt = 0
    absent_cnt = 0
    excused_cnt = 0

    for att, meeting in rows:
        if att.status == AttendanceStatus.PRESENT:
            present_cnt += 1
        elif att.status == AttendanceStatus.ABSENT:
            absent_cnt += 1
        elif att.status == AttendanceStatus.EXCUSED:
            excused_cnt += 1

        records.append(
            MemberAttendanceRecord(
                meeting_id=meeting.id,
                meeting_date=meeting.meeting_date,
                agenda=meeting.agenda,
                status=att.status,
                recorded_at=att.created_at.isoformat() if att.created_at else None,
            )
        )

    tot = len(records)
    rate = f"{(present_cnt / tot * 100):.1f}%" if tot > 0 else "0.0%"

    return MemberAttendanceResponse(
        member_id=member.id,
        member_name=member.full_name,
        summary=MemberAttendanceSummary(
            total_meetings=tot,
            present_count=present_cnt,
            absent_count=absent_cnt,
            excused_count=excused_cnt,
            attendance_rate=rate,
        ),
        records=records,
    )
