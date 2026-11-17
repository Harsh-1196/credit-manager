import uuid
from decimal import Decimal

from app.core.money import money_to_str, quantize_money
from app.db.models.loans import Loan, LoanScheduleStatus
from app.db.models.meetings import AttendanceStatus, Meeting
from app.db.models.savings import SavingsDue
from app.db.models.shg import SHG, GroupSettings, Member
from app.schemas.meetings import (
    CollectionSheetMemberRow,
    CollectionSheetResponse,
    CollectionSheetTotals,
)


def build_collection_sheet(
    meeting: Meeting,
    shg: SHG,
    settings: GroupSettings | None,
    members: list[Member],
    attendance_map: dict[uuid.UUID, AttendanceStatus],
    savings_dues_map: dict[uuid.UUID, SavingsDue],
    active_loans_map: dict[uuid.UUID, Loan],
    period: str,
) -> CollectionSheetResponse:
    """
    Pure domain logic: Assembles the collection sheet per SPEC sections 8, 11, and 12.5.
    Calculates per-member:
      - Savings due for the period
      - EMI due (current active installment: principal + interest)
      - Arrears (past-due installments)
      - Fines and penalties due
      - Total to collect
    """
    default_monthly_savings = settings.monthly_saving_amount if settings else Decimal("100.00")
    fine_grace_days = settings.fine_grace_days if settings else 5
    late_fine_per_day = settings.late_fine_per_day if settings else Decimal("1.00")
    max_late_fine = default_monthly_savings

    member_rows: list[CollectionSheetMemberRow] = []

    tot_savings_due = Decimal("0.00")
    tot_emi_due = Decimal("0.00")
    tot_arrears = Decimal("0.00")
    tot_fines_due = Decimal("0.00")
    tot_grand_due = Decimal("0.00")

    for m in members:
        # 1. Attendance
        att_status = attendance_map.get(m.id, AttendanceStatus.PRESENT)

        # 2. Savings due for the period
        s_due_record = savings_dues_map.get(m.id)
        if s_due_record:
            rem_savings = max(Decimal("0.00"), s_due_record.amount_due - s_due_record.amount_paid)
        else:
            rem_savings = quantize_money(default_monthly_savings)

        # 3. Savings late fines if overdue
        savings_fine = Decimal("0.00")
        if s_due_record and rem_savings > Decimal("0.00"):
            # Check period vs meeting date
            period_year, period_month = int(s_due_record.period[:4]), int(s_due_record.period[5:7])
            # If period is earlier than meeting month or meeting day is past grace
            from datetime import date
            period_due_date = date(period_year, period_month, 10)  # Standard 10th of the month
            if meeting.meeting_date > period_due_date:
                days_late = (meeting.meeting_date - period_due_date).days
                if days_late > fine_grace_days:
                    chargeable_days = days_late - fine_grace_days
                    raw_fine = Decimal(chargeable_days) * late_fine_per_day
                    savings_fine = min(max_late_fine, quantize_money(raw_fine))

        # 4. Loan calculations
        active_loan = active_loans_map.get(m.id)
        loan_p_due = Decimal("0.00")
        loan_i_due = Decimal("0.00")
        loan_emi_due = Decimal("0.00")
        loan_arrears = Decimal("0.00")
        loan_penalty = Decimal("0.00")
        active_loan_id: uuid.UUID | None = None
        active_loan_number: str | None = None

        if active_loan:
            active_loan_id = active_loan.id
            active_loan_number = active_loan.loan_number

            # Sort schedule by installment_no
            sched = sorted(active_loan.schedule, key=lambda s: s.installment_no)

            overdue_items = [
                s
                for s in sched
                if s.status == LoanScheduleStatus.OVERDUE
                or (
                    s.due_date < meeting.meeting_date
                    and (s.principal_paid + s.interest_paid < s.total_due)
                )
            ]

            arr_p = sum(max(Decimal("0.00"), s.principal_due - s.principal_paid) for s in overdue_items)
            arr_i = sum(max(Decimal("0.00"), s.interest_due - s.interest_paid) for s in overdue_items)
            loan_arrears = quantize_money(arr_p + arr_i)

            # Accrued penalties on loan schedule
            loan_penalty = quantize_money(
                sum(max(Decimal("0.00"), s.penalty_due - s.penalty_paid) for s in sched)
            )

            # Next current unpaid installment (not overdue)
            current_items = [
                s
                for s in sched
                if s not in overdue_items and (s.principal_paid + s.interest_paid < s.total_due)
            ]

            if current_items:
                next_inst = current_items[0]
                loan_p_due = quantize_money(max(Decimal("0.00"), next_inst.principal_due - next_inst.principal_paid))
                loan_i_due = quantize_money(max(Decimal("0.00"), next_inst.interest_due - next_inst.interest_paid))
                loan_emi_due = quantize_money(loan_p_due + loan_i_due)
            else:
                loan_p_due = Decimal("0.00")
                loan_i_due = Decimal("0.00")
                loan_emi_due = Decimal("0.00")

        # 5. Total fines due (savings fine + loan penalty)
        total_member_fines = quantize_money(savings_fine + loan_penalty)

        # 6. Total due for member
        row_total = quantize_money(rem_savings + loan_emi_due + loan_arrears + total_member_fines)

        # Update totals
        tot_savings_due += rem_savings
        tot_emi_due += loan_emi_due
        tot_arrears += loan_arrears
        tot_fines_due += total_member_fines
        tot_grand_due += row_total

        member_rows.append(
            CollectionSheetMemberRow(
                member_id=m.id,
                member_name=m.full_name,
                attendance_status=att_status,
                savings_due=money_to_str(rem_savings),
                emi_due=money_to_str(loan_emi_due),
                principal_due=money_to_str(loan_p_due),
                interest_due=money_to_str(loan_i_due),
                arrears=money_to_str(loan_arrears),
                penalty_due=money_to_str(loan_penalty),
                fines_due=money_to_str(total_member_fines),
                total_due=money_to_str(row_total),
                active_loan_id=active_loan_id,
                active_loan_number=active_loan_number,
            )
        )

    # Sort member rows by name
    member_rows.sort(key=lambda r: r.member_name.lower())

    totals = CollectionSheetTotals(
        total_savings_due=money_to_str(quantize_money(tot_savings_due)),
        total_emi_due=money_to_str(quantize_money(tot_emi_due)),
        total_arrears=money_to_str(quantize_money(tot_arrears)),
        total_fines_due=money_to_str(quantize_money(tot_fines_due)),
        total_due=money_to_str(quantize_money(tot_grand_due)),
        member_count=len(member_rows),
    )

    return CollectionSheetResponse(
        meeting_id=meeting.id,
        shg_id=shg.id,
        shg_name=shg.name,
        meeting_date=meeting.meeting_date,
        status=meeting.status,
        period=period,
        members=member_rows,
        totals=totals,
    )
