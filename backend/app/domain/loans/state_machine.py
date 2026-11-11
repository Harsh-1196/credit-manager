from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.db.models.auth import User, UserRole
from app.db.models.loans import Loan, LoanStatus, LoanStatusHistory
from app.domain.loans.eligibility import evaluate_loan_eligibility

# Valid state transitions mapped as {from_status: set(to_statuses)}
VALID_TRANSITIONS: dict[LoanStatus, set[LoanStatus]] = {
    LoanStatus.DRAFT: {LoanStatus.SUBMITTED},
    LoanStatus.SUBMITTED: {LoanStatus.APPROVED, LoanStatus.REJECTED},
    LoanStatus.APPROVED: {LoanStatus.DISBURSED, LoanStatus.REJECTED},
    LoanStatus.DISBURSED: {LoanStatus.ACTIVE},
    LoanStatus.ACTIVE: {LoanStatus.OVERDUE, LoanStatus.CLOSED},
    LoanStatus.OVERDUE: {LoanStatus.ACTIVE, LoanStatus.CLOSED, LoanStatus.WRITTEN_OFF},
    LoanStatus.CLOSED: set(),
    LoanStatus.WRITTEN_OFF: set(),
    LoanStatus.REJECTED: set(),
}


class LoanStateMachine:
    """
    Enforces the loan lifecycle state machine per SPEC section 6.1.
    All transitions are validated, write to loan_status_history, record an audit log,
    and increment the optimistic concurrency control version counter.
    """

    @classmethod
    async def transition(
        cls,
        db: AsyncSession,
        loan: Loan,
        to_status: LoanStatus,
        actor: User,
        reason: str | None = None,
        expected_version: int | None = None,
    ) -> Loan:
        from_status = loan.status

        # 1. Optimistic concurrency control check
        if expected_version is not None and loan.version != expected_version:
            raise AppError(
                code="OPTIMISTIC_LOCK_CONFLICT",
                message=(
                    f"Loan {loan.loan_number} was modified concurrently by another process. "
                    f"Expected version {expected_version}, but current version is {loan.version}."
                ),
                status_code=409,
                details={
                    "loan_id": str(loan.id),
                    "expected_version": expected_version,
                    "current_version": loan.version,
                },
            )

        # 2. Transition validity check
        allowed_targets = VALID_TRANSITIONS.get(from_status, set())
        if to_status not in allowed_targets:
            raise AppError(
                code="LOAN_INVALID_TRANSITION",
                message=f"Invalid loan transition from '{from_status.value}' to '{to_status.value}'.",
                status_code=400,
                details={
                    "loan_id": str(loan.id),
                    "from_status": from_status.value,
                    "to_status": to_status.value,
                    "allowed_transitions": [s.value for s in allowed_targets],
                },
            )

        # 3. Specific transition business rules & role checks
        now = datetime.now(UTC)

        # Transition: DRAFT -> SUBMITTED
        if to_status == LoanStatus.SUBMITTED:
            # Evaluate eligibility blockers before submission
            eval_res = await evaluate_loan_eligibility(
                db=db,
                shg_id=loan.shg_id,
                member_id=loan.member_id,
                principal=loan.principal,
                tenure_months=loan.tenure_months,
                exclude_loan_id=loan.id,
            )
            if not eval_res.is_eligible:
                blocker_reasons = [
                    c.message for c in eval_res.checks if c.severity == "BLOCKER" and not c.passed
                ]
                raise AppError(
                    code="LOAN_INELIGIBLE",
                    message="Loan application does not meet group eligibility criteria.",
                    status_code=400,
                    details={"blockers": blocker_reasons},
                )
            loan.applied_at = now

        # Transition: SUBMITTED -> APPROVED
        elif to_status == LoanStatus.APPROVED:
            # Check approver permissions
            if actor.role not in [UserRole.ADMIN, UserRole.GROUP_LEADER]:
                raise AppError(
                    code="UNAUTHORIZED",
                    message="Only GROUP_LEADER or ADMIN can approve loan applications.",
                    status_code=403,
                )

            # Maker-checker validation: Creator or applicant member cannot approve!
            cls._enforce_maker_checker(loan, actor)

            loan.approved_by = actor.id
            loan.approved_at = now

        # Transition: SUBMITTED -> REJECTED (or APPROVED -> REJECTED before disbursal)
        elif to_status == LoanStatus.REJECTED:
            if not reason or not reason.strip():
                raise AppError(
                    code="REASON_REQUIRED",
                    message="A descriptive reason is required to reject a loan application.",
                    status_code=400,
                )
            if actor.role not in [UserRole.ADMIN, UserRole.GROUP_LEADER]:
                raise AppError(
                    code="UNAUTHORIZED",
                    message="Only GROUP_LEADER or ADMIN can reject loan applications.",
                    status_code=403,
                )
            loan.rejection_reason = reason.strip()

        # Transition: OVERDUE -> WRITTEN_OFF
        elif to_status == LoanStatus.WRITTEN_OFF:
            if actor.role != UserRole.ADMIN:
                raise AppError(
                    code="FORBIDDEN_ROLE",
                    message="Only an ADMIN can write off a loan.",
                    status_code=403,
                )
            if not reason or not reason.strip():
                raise AppError(
                    code="REASON_REQUIRED",
                    message="A formal reason is required to write off a loan.",
                    status_code=400,
                )

        # Transition: CLOSED
        elif to_status == LoanStatus.CLOSED:
            loan.closed_at = now

        # 4. Apply status update and increment optimistic version
        loan.status = to_status
        loan.version += 1

        # 5. Record status history entry (append-only)
        history_entry = LoanStatusHistory(
            loan_id=loan.id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor.id,
            reason=reason.strip() if reason else None,
        )
        db.add(history_entry)

        # 6. Record audit log
        await record_audit_log(
            db=db,
            action=f"LOAN_{to_status.value}",
            entity_type="loans",
            entity_id=loan.id,
            before={"status": from_status.value, "version": loan.version - 1},
            after={"status": to_status.value, "version": loan.version, "reason": reason},
            actor_id=actor.id,
            actor_role=actor.role.value,
        )

        await db.flush()
        return loan

    @classmethod
    def _enforce_maker_checker(cls, loan: Loan, actor: User) -> None:
        """
        Enforces maker-checker rule per SPEC 2 and 6.1:
        A leader or admin cannot approve a loan they themselves applied for or created.
        """
        # Condition A: Actor is the user who created/submitted the application
        if loan.applied_by == actor.id:
            raise AppError(
                code="MAKER_CHECKER_VIOLATION",
                message=(
                    "Maker-checker violation: You created this loan application and cannot approve it. "
                    "Another group leader or an administrator must approve it."
                ),
                status_code=403,
                details={
                    "loan_id": str(loan.id),
                    "applied_by": str(loan.applied_by),
                    "actor_id": str(actor.id),
                },
            )

        # Condition B: Actor is linked to the borrower Member record
        if loan.member and loan.member.user_id == actor.id:
            raise AppError(
                code="MAKER_CHECKER_VIOLATION",
                message=(
                    "Maker-checker violation: You are the applicant borrower and cannot approve your own loan. "
                    "Another group leader or an administrator must approve it."
                ),
                status_code=403,
                details={
                    "loan_id": str(loan.id),
                    "member_user_id": str(loan.member.user_id),
                    "actor_id": str(actor.id),
                },
            )
