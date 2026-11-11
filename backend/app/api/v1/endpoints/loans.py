import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import check_user_has_group_access, get_current_user
from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.core.idempotency import (
    check_idempotency,
    compute_request_hash,
    save_idempotency_record,
)
from app.core.money import money_to_str, quantize_money
from app.db.models.auth import User, UserGroupAccess, UserRole
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus, LoanStatusHistory
from app.db.models.shg import GroupSettings, Member
from app.db.session import get_db
from app.domain.loans.eligibility import evaluate_loan_eligibility
from app.domain.loans.metrics import calculate_loan_summary_figures, calculate_portfolio_metrics
from app.domain.loans.schedule import calculate_loan_schedule
from app.domain.loans.state_machine import LoanStateMachine
from app.schemas.loans import (
    EligibilityCheckItemResponse,
    EligibilityResponse,
    LoanApproveRequest,
    LoanCreateRequest,
    LoanDetailResponse,
    LoanDisbursePreviewResponse,
    LoanDisburseRequest,
    LoanPreviewScheduleRequest,
    LoanPreviewScheduleResponse,
    LoanRejectRequest,
    LoanRepayPreviewRequest,
    LoanRepayPreviewResponse,
    LoanRepayRequest,
    LoanResponse,
    LoanScheduleItemResponse,
    LoanStatusHistoryResponse,
    LoanSummaryFiguresResponse,
    LoanWriteOffRequest,
    PortfolioMetricsResponse,
)
from app.services.loans import (
    disburse_loan,
    get_disburse_preview,
    get_repayment_preview,
    repay_loan,
    write_off_loan,
)

router = APIRouter(tags=["loans"])


def _populate_maker_checker(loan: Loan, current_user: User) -> tuple[bool, str | None]:
    """
    Computes whether the current user is eligible to approve the loan
    under the non-negotiable maker-checker policy (SPEC 2 and 6.1).
    """
    if loan.status != LoanStatus.SUBMITTED:
        return False, f"Loan is in {loan.status.value} status, not pending approval."

    if current_user.role not in [UserRole.ADMIN, UserRole.GROUP_LEADER]:
        return False, "Only group leaders or administrators can approve loans."

    if loan.applied_by == current_user.id:
        return (
            False,
            "Maker-checker restriction: You created this loan application and cannot approve it. Another leader or admin must approve.",
        )

    if loan.member and loan.member.user_id == current_user.id:
        return (
            False,
            "Maker-checker restriction: You are the applicant borrower and cannot approve your own loan.",
        )

    return True, None


def _serialize_loan(loan: Loan, current_user: User) -> LoanResponse:
    can_approve, note = _populate_maker_checker(loan, current_user)
    return LoanResponse(
        id=loan.id,
        shg_id=loan.shg_id,
        member_id=loan.member_id,
        member_name=loan.member.full_name if loan.member else None,
        loan_number=loan.loan_number,
        purpose=loan.purpose,
        principal=money_to_str(loan.principal),
        interest_rate=str(loan.interest_rate),
        interest_type=loan.interest_type,
        tenure_months=loan.tenure_months,
        processing_fee=money_to_str(loan.processing_fee),
        status=loan.status,
        applied_by=loan.applied_by,
        applied_at=loan.applied_at,
        approved_by=loan.approved_by,
        approved_at=loan.approved_at,
        rejection_reason=loan.rejection_reason,
        disbursed_at=loan.disbursed_at,
        disbursed_by=loan.disbursed_by,
        first_due_date=loan.first_due_date,
        closed_at=loan.closed_at,
        written_off_at=loan.written_off_at,
        written_off_by=loan.written_off_by,
        write_off_reason=loan.write_off_reason,
        version=loan.version,
        created_at=loan.created_at,
        can_approve=can_approve,
        maker_checker_note=note,
    )


@router.post("/loans/preview-schedule", response_model=LoanPreviewScheduleResponse)
async def preview_loan_schedule(
    payload: LoanPreviewScheduleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanPreviewScheduleResponse:
    """
    Calculates and previews the repayment schedule and optional eligibility analysis
    without persisting records to the database.
    """
    has_access = await check_user_has_group_access(current_user, payload.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Group not found.", status_code=status.HTTP_404_NOT_FOUND)

    schedule_res = calculate_loan_schedule(
        principal=payload.principal,
        annual_rate=payload.annual_rate,
        interest_type=payload.interest_type,
        tenure_months=payload.tenure_months,
        first_due_date=payload.first_due_date,
    )

    eligibility_resp: EligibilityResponse | None = None
    if payload.member_id:
        if current_user.role == UserRole.MEMBER:
            m_chk_stmt = select(Member).where(Member.id == payload.member_id, Member.shg_id == payload.shg_id)
            m_chk_res = await db.execute(m_chk_stmt)
            m_chk = m_chk_res.scalar_one_or_none()
            if not m_chk or m_chk.user_id != current_user.id:
                raise AppError(code="NOT_FOUND", message="Member not found.", status_code=status.HTTP_404_NOT_FOUND)

        eval_res = await evaluate_loan_eligibility(
            db=db,
            shg_id=payload.shg_id,
            member_id=payload.member_id,
            principal=payload.principal,
            tenure_months=payload.tenure_months,
        )
        eligibility_resp = EligibilityResponse(
            is_eligible=eval_res.is_eligible,
            has_warnings=eval_res.has_warnings,
            summary_message=eval_res.summary_message,
            checks=[
                EligibilityCheckItemResponse(
                    code=c.code,
                    name=c.name,
                    passed=c.passed,
                    severity=c.severity,
                    message=c.message,
                    actual_value=c.actual_value,
                    threshold_value=c.threshold_value,
                )
                for c in eval_res.checks
            ],
        )

    return LoanPreviewScheduleResponse(
        principal=money_to_str(schedule_res.principal),
        total_interest=money_to_str(schedule_res.total_interest),
        total_amount=money_to_str(schedule_res.total_amount),
        monthly_installment=money_to_str(schedule_res.monthly_installment),
        installments=[
            LoanScheduleItemResponse(
                installment_no=inst.installment_no,
                due_date=inst.due_date,
                principal_due=money_to_str(inst.principal_due),
                interest_due=money_to_str(inst.interest_due),
                total_due=money_to_str(inst.total_due),
                outstanding_balance=money_to_str(inst.outstanding_balance),
            )
            for inst in schedule_res.installments
        ],
        eligibility=eligibility_resp,
    )


@router.post("/loans", response_model=LoanResponse, status_code=status.HTTP_201_CREATED)
async def create_loan_application(
    payload: LoanCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> LoanResponse:
    """
    Creates a new loan application in DRAFT status, optionally submitting it immediately.
    """
    has_access = await check_user_has_group_access(current_user, payload.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Group not found.", status_code=status.HTTP_404_NOT_FOUND)

    if current_user.role == UserRole.AUDITOR:
        raise AppError(
            code="UNAUTHORIZED",
            message="Auditors cannot create loan applications.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Verify Member exists and belongs to group
    member_stmt = select(Member).where(
        Member.id == payload.member_id,
        Member.shg_id == payload.shg_id,
        Member.deleted_at.is_(None),
    )
    m_res = await db.execute(member_stmt)
    member = m_res.scalar_one_or_none()

    if not member:
        raise AppError(code="NOT_FOUND", message="Member not found.", status_code=status.HTTP_404_NOT_FOUND)

    # Member role can only apply for themselves
    if current_user.role == UserRole.MEMBER and member.user_id != current_user.id:
        raise AppError(
            code="UNAUTHORIZED",
            message="Members can only create loan applications for themselves.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # Compute processing fee from group settings
    settings_stmt = select(GroupSettings).where(GroupSettings.shg_id == payload.shg_id)
    set_res = await db.execute(settings_stmt)
    group_settings = set_res.scalar_one_or_none()
    fee_pct = group_settings.processing_fee_percent if group_settings else Decimal("1.000")
    processing_fee = quantize_money(payload.principal * (fee_pct / Decimal(100)))

    # Generate loan number: LN-{group_count + 1:04d}
    count_stmt = select(func.count()).select_from(Loan).where(Loan.shg_id == payload.shg_id)
    count_res = await db.execute(count_stmt)
    seq = (count_res.scalar() or 0) + 1
    loan_number = f"LN-{seq:04d}"

    loan = Loan(
        shg_id=payload.shg_id,
        member_id=payload.member_id,
        loan_number=loan_number,
        purpose=payload.purpose,
        principal=quantize_money(payload.principal),
        interest_rate=payload.interest_rate,
        interest_type=payload.interest_type,
        tenure_months=payload.tenure_months,
        processing_fee=processing_fee,
        status=LoanStatus.DRAFT,
        applied_by=current_user.id,
        first_due_date=payload.first_due_date,
        version=1,
    )
    db.add(loan)
    await db.flush()

    # Pre-generate tentative loan schedule installments
    sched_calc = calculate_loan_schedule(
        principal=loan.principal,
        annual_rate=loan.interest_rate,
        interest_type=loan.interest_type,
        tenure_months=loan.tenure_months,
        first_due_date=payload.first_due_date,
    )
    for inst in sched_calc.installments:
        db.add(
            LoanSchedule(
                loan_id=loan.id,
                installment_no=inst.installment_no,
                due_date=inst.due_date,
                principal_due=inst.principal_due,
                interest_due=inst.interest_due,
                total_due=inst.total_due,
                principal_paid=Decimal("0.00"),
                interest_paid=Decimal("0.00"),
                penalty_paid=Decimal("0.00"),
            )
        )
    await db.flush()

    await record_audit_log(
        db=db,
        action="LOAN_CREATED",
        entity_type="loans",
        entity_id=loan.id,
        after={
            "loan_number": loan_number,
            "member_id": str(loan.member_id),
            "principal": str(loan.principal),
            "tenure_months": loan.tenure_months,
            "status": loan.status.value,
        },
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )

    if payload.submit_immediately:
        await LoanStateMachine.transition(
            db=db,
            loan=loan,
            to_status=LoanStatus.SUBMITTED,
            actor=current_user,
            reason="Submitted upon creation",
            expected_version=loan.version,
        )

    await db.commit()
    request.state.audit_logged = True

    # Re-fetch with member
    re_stmt = select(Loan).options(selectinload(Loan.member)).where(Loan.id == loan.id)
    re_res = await db.execute(re_stmt)
    full_loan = re_res.scalar_one()

    return _serialize_loan(full_loan, current_user)


@router.post("/loans/{id}/submit", response_model=LoanResponse)
async def submit_loan_application(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> LoanResponse:
    """
    Submits a draft loan application for approval after verifying eligibility criteria.
    """
    if current_user.role == UserRole.AUDITOR:
        raise AppError(code="UNAUTHORIZED", message="Auditors cannot submit loan applications.", status_code=403)

    stmt = select(Loan).options(selectinload(Loan.member)).where(Loan.id == id).with_for_update().with_for_update()
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()

    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    # Member can only submit own application
    if current_user.role == UserRole.MEMBER and (
        loan.applied_by != current_user.id
        and (loan.member is None or loan.member.user_id != current_user.id)
    ):
        raise AppError(code="UNAUTHORIZED", message="Cannot submit another user's loan.", status_code=403)

    await LoanStateMachine.transition(
        db=db,
        loan=loan,
        to_status=LoanStatus.SUBMITTED,
        actor=current_user,
        reason="Application submitted for approval",
        expected_version=loan.version,
    )

    await db.commit()
    request.state.audit_logged = True
    return _serialize_loan(loan, current_user)


@router.post("/loans/{id}/approve", response_model=LoanResponse)
async def approve_loan_application(
    id: uuid.UUID,
    payload: LoanApproveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> LoanResponse:
    """
    Approves a submitted loan application.
    Enforces strict maker-checker policy (creator or applicant cannot approve)
    and optimistic locking with version.
    """
    stmt = select(Loan).options(selectinload(Loan.member)).where(Loan.id == id).with_for_update()
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()

    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    await LoanStateMachine.transition(
        db=db,
        loan=loan,
        to_status=LoanStatus.APPROVED,
        actor=current_user,
        reason=payload.reason,
        expected_version=payload.version,
    )

    await db.commit()
    request.state.audit_logged = True
    return _serialize_loan(loan, current_user)


@router.post("/loans/{id}/reject", response_model=LoanResponse)
async def reject_loan_application(
    id: uuid.UUID,
    payload: LoanRejectRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> LoanResponse:
    """
    Rejects a submitted or approved loan application. Requires a mandatory explanatory reason.
    """
    stmt = select(Loan).options(selectinload(Loan.member)).where(Loan.id == id).with_for_update()
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()

    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    await LoanStateMachine.transition(
        db=db,
        loan=loan,
        to_status=LoanStatus.REJECTED,
        actor=current_user,
        reason=payload.reason,
        expected_version=payload.version,
    )

    await db.commit()
    request.state.audit_logged = True
    return _serialize_loan(loan, current_user)


@router.get("/loans/{id}", response_model=LoanDetailResponse)
async def get_loan_detail(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanDetailResponse:
    """
    Retrieves full loan details including schedule, history, eligibility status,
    and maker-checker approval capability for the caller.
    """
    stmt = (
        select(Loan)
        .options(
            selectinload(Loan.member),
            selectinload(Loan.schedule),
            selectinload(Loan.history),
        )
        .where(Loan.id == id)
    )
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()

    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    # If member role, ensure viewing own loan
    if current_user.role == UserRole.MEMBER and (
        loan.member is None or loan.member.user_id != current_user.id
    ):
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    # Evaluate eligibility checks for context
    eval_res = await evaluate_loan_eligibility(
        db=db,
        shg_id=loan.shg_id,
        member_id=loan.member_id,
        principal=loan.principal,
        tenure_months=loan.tenure_months,
        exclude_loan_id=loan.id,
    )
    eligibility_resp = EligibilityResponse(
        is_eligible=eval_res.is_eligible,
        has_warnings=eval_res.has_warnings,
        summary_message=eval_res.summary_message,
        checks=[
            EligibilityCheckItemResponse(
                code=c.code,
                name=c.name,
                passed=c.passed,
                severity=c.severity,
                message=c.message,
                actual_value=c.actual_value,
                threshold_value=c.threshold_value,
            )
            for c in eval_res.checks
        ],
    )

    # Compute summary figures (outstanding principal, interest, penalty, next due date, days overdue)
    summary_data = await calculate_loan_summary_figures(db, loan)
    summary_resp = LoanSummaryFiguresResponse(
        outstanding_principal=money_to_str(summary_data.outstanding_principal),
        outstanding_interest=money_to_str(summary_data.outstanding_interest),
        outstanding_penalty=money_to_str(summary_data.outstanding_penalty),
        total_outstanding_balance=money_to_str(summary_data.total_outstanding_balance),
        total_principal_paid=money_to_str(summary_data.total_principal_paid),
        total_interest_paid=money_to_str(summary_data.total_interest_paid),
        total_penalty_paid=money_to_str(summary_data.total_penalty_paid),
        next_due_date=summary_data.next_due_date,
        next_due_amount=money_to_str(summary_data.next_due_amount),
        days_overdue=summary_data.days_overdue,
    )

    base = _serialize_loan(loan, current_user)
    today_date = date.today()
    return LoanDetailResponse(
        **base.model_dump(),
        schedule=[
            LoanScheduleItemResponse(
                installment_no=inst.installment_no,
                due_date=inst.due_date,
                principal_due=money_to_str(inst.principal_due),
                interest_due=money_to_str(inst.interest_due),
                total_due=money_to_str(inst.total_due),
                outstanding_balance=money_to_str(
                    max(Decimal("0.00"), inst.principal_due - inst.principal_paid)
                ),
                principal_paid=money_to_str(inst.principal_paid),
                interest_paid=money_to_str(inst.interest_paid),
                penalty_paid=money_to_str(inst.penalty_paid),
                penalty_due=money_to_str(inst.penalty_due),
                status=inst.status,
                days_overdue=(today_date - inst.due_date).days
                if inst.status != LoanScheduleStatus.PAID and inst.due_date < today_date
                else 0,
            )
            for inst in loan.schedule
        ],
        history=[
            LoanStatusHistoryResponse(
                id=h.id,
                loan_id=h.loan_id,
                from_status=h.from_status,
                to_status=h.to_status,
                actor_id=h.actor_id,
                reason=h.reason,
                created_at=h.created_at,
            )
            for h in loan.history
        ],
        eligibility=eligibility_resp,
        summary=summary_resp,
    )


@router.get("/loans", response_model=list[LoanResponse])
async def list_loans(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    group_id: uuid.UUID | None = Query(default=None),
    member_id: uuid.UUID | None = Query(default=None),
    loan_status: LoanStatus | None = Query(default=None, alias="status"),
) -> list[LoanResponse]:
    """
    Lists loans with optional filters, strictly scoped to caller's permitted groups.
    """
    stmt = (
        select(Loan)
        .options(selectinload(Loan.member))
        .order_by(Loan.created_at.desc())
    )

    if group_id:
        has_access = await check_user_has_group_access(current_user, group_id, db)
        if not has_access:
            return []
        stmt = stmt.where(Loan.shg_id == group_id)
    elif current_user.role != UserRole.ADMIN:
        subquery = select(UserGroupAccess.group_id).where(UserGroupAccess.user_id == current_user.id)
        stmt = stmt.where(Loan.shg_id.in_(subquery))

    if member_id:
        stmt = stmt.where(Loan.member_id == member_id)

    if loan_status:
        stmt = stmt.where(Loan.status == loan_status)

    # For MEMBER role: only show own loans
    if current_user.role == UserRole.MEMBER:
        m_stmt = select(Member.id).where(Member.user_id == current_user.id)
        m_res = await db.execute(m_stmt)
        my_member_ids = list(m_res.scalars().all())
        stmt = stmt.where(Loan.member_id.in_(my_member_ids))

    res = await db.execute(stmt)
    loans = res.scalars().all()

    return [_serialize_loan(loan_obj, current_user) for loan_obj in loans]


@router.get("/loans/{id}/history", response_model=list[LoanStatusHistoryResponse])
async def get_loan_history(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LoanStatusHistoryResponse]:
    """
    Retrieves the chronological append-only status transition history for a loan.
    """
    stmt = select(Loan).options(selectinload(Loan.member)).where(Loan.id == id)
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()

    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    if current_user.role == UserRole.MEMBER and (
        loan.member is None or loan.member.user_id != current_user.id
    ):
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    hist_stmt = (
        select(LoanStatusHistory)
        .where(LoanStatusHistory.loan_id == id)
        .order_by(LoanStatusHistory.created_at.asc())
    )
    hist_res = await db.execute(hist_stmt)
    history = hist_res.scalars().all()

    return [
        LoanStatusHistoryResponse(
            id=h.id,
            loan_id=h.loan_id,
            from_status=h.from_status,
            to_status=h.to_status,
            actor_id=h.actor_id,
            reason=h.reason,
            created_at=h.created_at,
        )
        for h in history
    ]


@router.get("/loans/metrics/portfolio", response_model=PortfolioMetricsResponse)
async def get_portfolio_metrics(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    shg_id: uuid.UUID | None = Query(default=None),
    as_of_date: date | None = Query(default=None),
) -> PortfolioMetricsResponse:
    """
    Computes live portfolio quality metrics including PAR 30/60/90.
    Scoped by user's permitted groups.
    """
    if current_user.role == UserRole.MEMBER:
        raise AppError(code="UNAUTHORIZED", message="Members cannot view group portfolio metrics.", status_code=status.HTTP_403_FORBIDDEN)

    allowed_shg_ids: list[uuid.UUID] | None = None
    if shg_id:
        has_access = await check_user_has_group_access(current_user, shg_id, db)
        if not has_access:
            raise AppError(code="NOT_FOUND", message="Group not found.", status_code=status.HTTP_404_NOT_FOUND)
    elif current_user.role != UserRole.ADMIN:
        u_stmt = select(UserGroupAccess.group_id).where(UserGroupAccess.user_id == current_user.id)
        u_res = await db.execute(u_stmt)
        allowed_shg_ids = list(u_res.scalars().all())

    metrics = await calculate_portfolio_metrics(
        db,
        shg_id=shg_id,
        allowed_shg_ids=allowed_shg_ids,
        as_of_date=as_of_date,
    )
    return PortfolioMetricsResponse(
        shg_id=metrics.shg_id,
        as_of_date=metrics.as_of_date,
        total_loans_count=metrics.total_loans_count,
        active_loans_count=metrics.active_loans_count,
        overdue_loans_count=metrics.overdue_loans_count,
        closed_loans_count=metrics.closed_loans_count,
        written_off_loans_count=metrics.written_off_loans_count,
        total_disbursed_principal=money_to_str(metrics.total_disbursed_principal),
        total_principal_repaid=money_to_str(metrics.total_principal_repaid),
        total_outstanding_principal=money_to_str(metrics.total_outstanding_principal),
        total_overdue_principal=money_to_str(metrics.total_overdue_principal),
        total_interest_outstanding=money_to_str(metrics.total_interest_outstanding),
        total_penalty_outstanding=money_to_str(metrics.total_penalty_outstanding),
        par_30_principal=money_to_str(metrics.par_30_principal),
        par_30_count=metrics.par_30_count,
        par_30_ratio=f"{metrics.par_30_ratio:.2f}%",
        par_60_principal=money_to_str(metrics.par_60_principal),
        par_60_count=metrics.par_60_count,
        par_60_ratio=f"{metrics.par_60_ratio:.2f}%",
        par_90_principal=money_to_str(metrics.par_90_principal),
        par_90_count=metrics.par_90_count,
        par_90_ratio=f"{metrics.par_90_ratio:.2f}%",
    )


@router.get("/loans/{id}/disburse-preview", response_model=LoanDisbursePreviewResponse)
async def get_loan_disburse_preview(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanDisbursePreviewResponse:
    """
    Returns preview of journal lines to be posted and checks group cash sufficiency.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.GROUP_LEADER]:
        raise AppError(code="UNAUTHORIZED", message="Only GROUP_LEADER or ADMIN can view disbursal previews.", status_code=status.HTTP_403_FORBIDDEN)
    stmt = select(Loan).where(Loan.id == id)
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    preview_dict = await get_disburse_preview(db, loan.id, loan.shg_id)
    return LoanDisbursePreviewResponse(**preview_dict)


@router.post("/loans/{id}/disburse", response_model=LoanResponse)
async def disburse_loan_endpoint(
    id: uuid.UUID,
    payload: LoanDisburseRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> LoanResponse | Response:
    """
    Disburses an approved loan per SPEC sections 6.1 and 14:
    - Verifies cash sufficiency
    - Posts double-entry journal entry with locking
    - Generates schedule and moves to ACTIVE
    """
    stmt = select(Loan).where(Loan.id == id)
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    req_hash: str | None = None
    scope: str | None = None
    if payload.idempotency_key:
        scope = f"loan_disburse:{loan.shg_id}:{loan.id}"
        req_hash = compute_request_hash(payload.model_dump(mode="json"))
        cached = await check_idempotency(db, key=payload.idempotency_key, scope=scope, request_hash=req_hash)
        if cached:
            return Response(
                content=cached.response_body,
                status_code=cached.response_status,
                media_type="application/json",
            )

    disbursed_loan = await disburse_loan(
        db=db,
        loan_id=loan.id,
        shg_id=loan.shg_id,
        current_user=current_user,
        first_due_date=payload.first_due_date,
        expected_version=payload.version,
        idempotency_key=payload.idempotency_key,
    )
    await db.commit()
    request.state.audit_logged = True
    serialized = _serialize_loan(disbursed_loan, current_user)

    if payload.idempotency_key and scope and req_hash:
        await save_idempotency_record(
            db=db,
            key=payload.idempotency_key,
            scope=scope,
            request_hash=req_hash,
            response_status=status.HTTP_200_OK,
            response_body=serialized.model_dump_json(),
        )
        await db.commit()

    return serialized


@router.post("/loans/{id}/preview-repayment", response_model=LoanRepayPreviewResponse)
async def preview_loan_repayment(
    id: uuid.UUID,
    payload: LoanRepayPreviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoanRepayPreviewResponse:
    """
    Pre-calculates live repayment breakdown (penalty, interest, principal, prepayment)
    without modifying the database.
    """
    stmt = select(Loan).options(selectinload(Loan.member)).where(Loan.id == id)
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    if current_user.role == UserRole.MEMBER and (
        loan.member is None or loan.member.user_id != current_user.id
    ):
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    preview_res = await get_repayment_preview(
        db=db,
        loan_id=loan.id,
        shg_id=loan.shg_id,
        amount=payload.amount,
        payment_date=payload.payment_date,
    )
    return LoanRepayPreviewResponse(**preview_res)


@router.post("/loans/{id}/repay", response_model=LoanDetailResponse)
async def repay_loan_endpoint(
    id: uuid.UUID,
    payload: LoanRepayRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> LoanDetailResponse | Response:
    """
    Records a loan repayment per SPEC sections 6.4, 6.5, and 14:
    - Multi-line balanced journal entry
    - Row-level locking on loan & schedule
    - Idempotency support
    - Status progression and closure when settled
    """
    stmt = select(Loan).where(Loan.id == id)
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    req_hash: str | None = None
    scope: str | None = None
    if payload.idempotency_key:
        scope = f"loan_repay:{loan.shg_id}:{loan.id}"
        req_hash = compute_request_hash(payload.model_dump(mode="json"))
        cached = await check_idempotency(db, key=payload.idempotency_key, scope=scope, request_hash=req_hash)
        if cached:
            return Response(
                content=cached.response_body,
                status_code=cached.response_status,
                media_type="application/json",
            )

    updated_loan, alloc_res = await repay_loan(
        db=db,
        loan_id=loan.id,
        shg_id=loan.shg_id,
        current_user=current_user,
        amount=payload.amount,
        payment_date=payload.payment_date,
        expected_version=payload.version,
        idempotency_key=payload.idempotency_key,
    )

    await record_audit_log(
        db=db,
        action="LOAN_REPAYMENT",
        entity_type="loans",
        entity_id=loan.id,
        after={
            "loan_number": loan.loan_number,
            "payment_amount": str(alloc_res.total_payment),
            "principal_allocated": str(alloc_res.total_principal),
            "interest_allocated": str(alloc_res.total_interest),
            "penalty_allocated": str(alloc_res.total_penalty),
            "is_fully_paid": alloc_res.is_loan_fully_paid,
            "status": updated_loan.status.value,
        },
        request=request,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
    )

    await db.commit()
    request.state.audit_logged = True
    detail_res = await get_loan_detail(id=updated_loan.id, current_user=current_user, db=db)

    if payload.idempotency_key and scope and req_hash:
        await save_idempotency_record(
            db=db,
            key=payload.idempotency_key,
            scope=scope,
            request_hash=req_hash,
            response_status=status.HTTP_200_OK,
            response_body=detail_res.model_dump_json(),
        )
        await db.commit()

    return detail_res


@router.post("/loans/{id}/repayments", response_model=LoanDetailResponse, include_in_schema=False)
async def repay_loan_spec_alias(
    id: uuid.UUID,
    payload: LoanRepayRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> LoanDetailResponse | Response:
    """SPEC 8 exact path alias for repaying loans."""
    return await repay_loan_endpoint(id=id, payload=payload, current_user=current_user, db=db, request=request)


@router.get("/loans/{id}/schedule", response_model=list[LoanScheduleItemResponse])
async def get_loan_schedule(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LoanScheduleItemResponse]:
    """SPEC 8 standalone endpoint for retrieving repayment schedule."""
    detail = await get_loan_detail(id=id, current_user=current_user, db=db)
    return detail.schedule


@router.post("/loans/{id}/write-off", response_model=LoanResponse)
async def write_off_loan_endpoint(
    id: uuid.UUID,
    payload: LoanWriteOffRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> LoanResponse:
    """
    Writes off an overdue loan per SPEC section 6.1 (ADMIN only, reason required).
    """
    stmt = select(Loan).where(Loan.id == id)
    res = await db.execute(stmt)
    loan = res.scalar_one_or_none()
    if not loan:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    has_access = await check_user_has_group_access(current_user, loan.shg_id, db)
    if not has_access:
        raise AppError(code="NOT_FOUND", message="Loan not found.", status_code=status.HTTP_404_NOT_FOUND)

    written_off_loan = await write_off_loan(
        db=db,
        loan_id=loan.id,
        shg_id=loan.shg_id,
        current_user=current_user,
        reason=payload.reason,
        expected_version=payload.version,
    )
    await db.commit()
    request.state.audit_logged = True
    return _serialize_loan(written_off_loan, current_user)
