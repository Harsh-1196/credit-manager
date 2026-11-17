from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.core.money import quantize_money
from app.db.models.ledger import Account, AccountType, JournalEntry, JournalLine
from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.meetings import Attendance, AttendanceStatus, Meeting, MeetingStatus
from app.db.models.savings import SavingsDue, SavingsDueStatus
from app.db.models.shg import SHG, Member
from app.domain.loans.metrics import calculate_loan_summary_figures, calculate_portfolio_metrics
from app.domain.outbox.service import get_or_create_dashboard_read_model
from app.domain.reports.schemas import (
    AgingBucketItem,
    CollectionDueItem,
    DisbursalVsRepaymentItem,
    GroupDashboardFigures,
    GroupDashboardReportResponse,
    GroupLedgerReportResponse,
    LoanPortfolioReportResponse,
    MemberStatementReportResponse,
    MemberStatementSummary,
    SavingsTrendItem,
)
from app.domain.savings.service import get_member_savings_balance


async def generate_group_dashboard_report(
    db: AsyncSession,
    shg_id: uuid.UUID,
    as_of_date: date | None = None,
) -> GroupDashboardReportResponse:
    as_of = as_of_date or date.today()

    shg = await db.get(SHG, shg_id)
    if not shg:
        raise AppError(code="SHG_NOT_FOUND", message=f"Group {shg_id} not found", status_code=404)

    read_model = await get_or_create_dashboard_read_model(db, shg_id)

    # 1. Total corpus: Cash account 1000 balance from journal lines
    stmt_cash = (
        select(
            func.coalesce(func.sum(JournalLine.debit), 0)
            - func.coalesce(func.sum(JournalLine.credit), 0)
        )
        .join(Account, JournalLine.account_id == Account.id)
        .where(Account.shg_id == shg_id, Account.code == "1000")
    )
    cash_val = (await db.execute(stmt_cash)).scalar()
    if cash_val is not None and cash_val != 0:
        total_corpus = quantize_money(Decimal(str(cash_val)))
    else:
        total_corpus = quantize_money(read_model.group_cash_balance)

    # 2. Total savings: Member savings sub-accounts (2000-*) credit balances from journal lines
    stmt_savings = (
        select(
            func.coalesce(func.sum(JournalLine.credit), 0)
            - func.coalesce(func.sum(JournalLine.debit), 0)
        )
        .join(Account, JournalLine.account_id == Account.id)
        .where(Account.shg_id == shg_id, Account.type == AccountType.LIABILITY)
    )
    savings_val = (await db.execute(stmt_savings)).scalar()
    if savings_val is not None and savings_val != 0:
        total_savings = quantize_money(Decimal(str(savings_val)))
    else:
        total_savings = quantize_money(read_model.total_savings)

    # 3. Portfolio metrics: outstanding principal, overdue amount, repayment rate
    port_metrics = await calculate_portfolio_metrics(db, shg_id=shg_id, as_of_date=as_of)
    outstanding_principal = port_metrics.total_outstanding_principal
    overdue_amount = port_metrics.total_overdue_principal

    # Repayment rate: total repaid / (total repaid + overdue principal)
    repaid_and_overdue = port_metrics.total_principal_repaid + port_metrics.total_overdue_principal
    if repaid_and_overdue > Decimal("0.00"):
        repayment_rate = quantize_money(
            (port_metrics.total_principal_repaid / repaid_and_overdue) * Decimal("100.0")
        )
    else:
        repayment_rate = Decimal("100.00")

    interest_earned = quantize_money(read_model.total_interest_collected)

    # 4. Next meeting
    stmt_next_meeting = (
        select(Meeting)
        .where(Meeting.shg_id == shg_id, Meeting.meeting_date >= as_of, Meeting.status == MeetingStatus.SCHEDULED)
        .order_by(Meeting.meeting_date.asc())
        .limit(1)
    )
    next_meeting = (await db.execute(stmt_next_meeting)).scalar_one_or_none()
    next_meeting_date = next_meeting.meeting_date if next_meeting else None

    # 5. Upcoming collections due
    stmt_dues = (
        select(SavingsDue, Member)
        .join(Member, SavingsDue.member_id == Member.id)
        .where(
            SavingsDue.shg_id == shg_id,
            SavingsDue.status.in_([SavingsDueStatus.PENDING, SavingsDueStatus.OVERDUE, SavingsDueStatus.PARTIAL]),
        )
    )
    savings_dues_res = (await db.execute(stmt_dues)).all()

    # Loan schedules due
    stmt_loan_dues = (
        select(LoanSchedule, Loan, Member)
        .join(Loan, LoanSchedule.loan_id == Loan.id)
        .join(Member, Loan.member_id == Member.id)
        .where(
            Loan.shg_id == shg_id,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]),
            LoanSchedule.status.in_([LoanScheduleStatus.PENDING, LoanScheduleStatus.OVERDUE, LoanScheduleStatus.PARTIAL]),
            LoanSchedule.due_date <= (as_of + timedelta(days=35)),
        )
    )
    loan_dues_res = (await db.execute(stmt_loan_dues)).all()

    # Group collections due by member
    member_due_map: dict[uuid.UUID, dict[str, Any]] = {}

    for sd, mem in savings_dues_res:
        if mem.id not in member_due_map:
            member_due_map[mem.id] = {
                "member_id": mem.id,
                "member_name": mem.full_name,
                "savings_due": Decimal("0.00"),
                "emi_due": Decimal("0.00"),
                "arrears": Decimal("0.00"),
                "fines": Decimal("0.00"),
                "total_due": Decimal("0.00"),
            }
        rem = quantize_money(sd.amount_due - sd.amount_paid)
        if sd.status == SavingsDueStatus.OVERDUE:
            member_due_map[mem.id]["arrears"] += rem
        else:
            member_due_map[mem.id]["savings_due"] += rem
        member_due_map[mem.id]["total_due"] += rem

    for ls, _loan, mem in loan_dues_res:
        if mem.id not in member_due_map:
            member_due_map[mem.id] = {
                "member_id": mem.id,
                "member_name": mem.full_name,
                "savings_due": Decimal("0.00"),
                "emi_due": Decimal("0.00"),
                "arrears": Decimal("0.00"),
                "fines": Decimal("0.00"),
                "total_due": Decimal("0.00"),
            }
        p_rem = ls.principal_due - ls.principal_paid
        i_rem = ls.interest_due - ls.interest_paid
        emi_rem = quantize_money(p_rem + i_rem)
        pen_rem = quantize_money(ls.penalty_due - ls.penalty_paid)
        if ls.status == LoanScheduleStatus.OVERDUE:
            member_due_map[mem.id]["arrears"] += emi_rem
        else:
            member_due_map[mem.id]["emi_due"] += emi_rem
        member_due_map[mem.id]["fines"] += pen_rem
        member_due_map[mem.id]["total_due"] += quantize_money(emi_rem + pen_rem)

    collections_due_list = [
        CollectionDueItem(
            member_id=v["member_id"],
            member_name=v["member_name"],
            savings_due=quantize_money(v["savings_due"]),
            emi_due=quantize_money(v["emi_due"]),
            arrears=quantize_money(v["arrears"]),
            fines=quantize_money(v["fines"]),
            total_due=quantize_money(v["total_due"]),
        )
        for v in member_due_map.values()
    ]
    collections_due_list.sort(key=lambda x: x.total_due, reverse=True)

    total_collections_due = sum((c.total_due for c in collections_due_list), Decimal("0.00"))

    # 6. Savings monthly trend (last 6 months)
    six_months_ago = as_of - timedelta(days=180)
    stmt_savings_trend = (
        select(
            JournalEntry.entry_date,
            JournalLine.credit,
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(Account, JournalLine.account_id == Account.id)
        .where(
            JournalEntry.shg_id == shg_id,
            JournalEntry.entry_date >= six_months_ago,
            Account.type == AccountType.LIABILITY,
            JournalLine.credit > 0,
        )
    )
    trend_rows = (await db.execute(stmt_savings_trend)).all()
    monthly_savings: dict[str, Decimal] = {}
    for entry_date, credit in trend_rows:
        m_str = entry_date.strftime("%Y-%m")
        monthly_savings[m_str] = monthly_savings.get(m_str, Decimal("0.00")) + Decimal(str(credit))

    # Fill any empty months
    curr = six_months_ago.replace(day=1)
    savings_trend: list[SavingsTrendItem] = []
    while curr <= as_of:
        m_str = curr.strftime("%Y-%m")
        savings_trend.append(
            SavingsTrendItem(month=m_str, amount=quantize_money(monthly_savings.get(m_str, Decimal("0.00"))))
        )
        # Advance 1 month
        if curr.month == 12:
            curr = curr.replace(year=curr.year + 1, month=1)
        else:
            curr = curr.replace(month=curr.month + 1)

    # 7. Disbursals vs Repayments monthly series
    six_months_ago_dt = datetime.combine(six_months_ago, datetime.min.time()).replace(tzinfo=UTC)
    stmt_disbursed = (
        select(Loan.disbursed_at, Loan.principal)
        .where(
            Loan.shg_id == shg_id,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE, LoanStatus.CLOSED, LoanStatus.WRITTEN_OFF]),
            Loan.disbursed_at.is_not(None),
            Loan.disbursed_at >= six_months_ago_dt,
        )
    )
    disb_rows = (await db.execute(stmt_disbursed)).all()
    monthly_disb: dict[str, Decimal] = {}
    for d_dt, princ in disb_rows:
        if d_dt:
            m_str = d_dt.strftime("%Y-%m")
            monthly_disb[m_str] = monthly_disb.get(m_str, Decimal("0.00")) + Decimal(str(princ))

    stmt_repaid = (
        select(JournalEntry.entry_date, JournalLine.credit)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(Account, JournalLine.account_id == Account.id)
        .where(
            JournalEntry.shg_id == shg_id,
            JournalEntry.entry_date >= six_months_ago,
            Account.type == AccountType.ASSET,
            Account.code.like("1100%"),
            JournalLine.credit > 0,
        )
    )
    repaid_rows = (await db.execute(stmt_repaid)).all()
    monthly_repaid: dict[str, Decimal] = {}
    for entry_date, credit in repaid_rows:
        m_str = entry_date.strftime("%Y-%m")
        monthly_repaid[m_str] = monthly_repaid.get(m_str, Decimal("0.00")) + Decimal(str(credit))

    disb_vs_repay: list[DisbursalVsRepaymentItem] = []
    for st in savings_trend:
        m_str = st.month
        disb_vs_repay.append(
            DisbursalVsRepaymentItem(
                month=m_str,
                disbursed=quantize_money(monthly_disb.get(m_str, Decimal("0.00"))),
                repaid=quantize_money(monthly_repaid.get(m_str, Decimal("0.00"))),
            )
        )

    # 8. Aging buckets
    stmt_active_loans = (
        select(Loan)
        .options(selectinload(Loan.schedule))
        .where(
            Loan.shg_id == shg_id,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]),
        )
    )
    active_loans = (await db.execute(stmt_active_loans)).scalars().all()

    buckets_data: dict[str, dict[str, Decimal | int]] = {
        "CURRENT": {"count": 0, "amount": Decimal("0.00")},
        "1-30": {"count": 0, "amount": Decimal("0.00")},
        "31-60": {"count": 0, "amount": Decimal("0.00")},
        "61-90": {"count": 0, "amount": Decimal("0.00")},
        "90+": {"count": 0, "amount": Decimal("0.00")},
    }

    for loan in active_loans:
        figs = await calculate_loan_summary_figures(db, loan, as_of_date=as_of)
        days = figs.days_overdue
        out_p = figs.outstanding_principal
        if days == 0:
            b_key = "CURRENT"
        elif days <= 30:
            b_key = "1-30"
        elif days <= 60:
            b_key = "31-60"
        elif days <= 90:
            b_key = "61-90"
        else:
            b_key = "90+"

        buckets_data[b_key]["count"] = int(buckets_data[b_key]["count"]) + 1
        buckets_data[b_key]["amount"] = Decimal(str(buckets_data[b_key]["amount"])) + out_p

    aging_buckets = [
        AgingBucketItem(
            bucket=k,
            count=int(v["count"]),
            amount=quantize_money(Decimal(str(v["amount"]))),
        )
        for k, v in buckets_data.items()
    ]

    return GroupDashboardReportResponse(
        shg_id=shg.id,
        shg_name=shg.name,
        as_of_date=as_of,
        figures=GroupDashboardFigures(
            total_corpus=total_corpus,
            total_savings=total_savings,
            outstanding_principal=quantize_money(outstanding_principal),
            interest_earned=interest_earned,
            repayment_rate=repayment_rate,
            overdue_amount=quantize_money(overdue_amount),
            next_meeting_date=next_meeting_date,
            collections_due_next_meeting=quantize_money(total_collections_due),
        ),
        savings_trend=savings_trend,
        disbursals_vs_repayments=disb_vs_repay,
        aging_buckets=aging_buckets,
        collections_due=collections_due_list,
    )


async def generate_member_statement_report(
    db: AsyncSession,
    member_id: uuid.UUID,
    from_date: date | None = None,
    to_date: date | None = None,
) -> MemberStatementReportResponse:
    member = await db.get(Member, member_id)
    if not member:
        raise AppError(code="MEMBER_NOT_FOUND", message=f"Member {member_id} not found", status_code=404)

    shg = await db.get(SHG, member.shg_id)
    shg_name = shg.name if shg else "Unknown Group"

    # Total savings balance via direct ledger balance
    total_savings = await get_member_savings_balance(db, member.shg_id, member.id)

    # Passbook entries
    code_pattern = f"2000-{str(member.id)[:8]}%"
    stmt_acc = select(Account).where(Account.shg_id == member.shg_id, Account.code.like(code_pattern))
    savings_acc = (await db.execute(stmt_acc)).scalar_one_or_none()

    passbook_entries: list[dict[str, Any]] = []
    if savings_acc:
        query_lines = (
            select(JournalLine, JournalEntry)
            .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
            .where(JournalLine.account_id == savings_acc.id)
            .order_by(JournalEntry.entry_date.asc(), JournalEntry.created_at.asc())
        )
        if from_date:
            query_lines = query_lines.where(JournalEntry.entry_date >= from_date)
        if to_date:
            query_lines = query_lines.where(JournalEntry.entry_date <= to_date)

        lines_res = (await db.execute(query_lines)).all()
        running_bal = Decimal("0.00")
        for line, entry in lines_res:
            running_bal += line.credit - line.debit
            passbook_entries.append({
                "date": entry.entry_date.isoformat(),
                "entry_number": f"JE-{str(entry.id)[:8]}",
                "particulars": entry.description,
                "debit": str(line.debit) if line.debit > 0 else "-",
                "credit": str(line.credit) if line.credit > 0 else "-",
                "balance": str(quantize_money(running_bal)),
            })

    # Loans
    stmt_loans = (
        select(Loan)
        .options(selectinload(Loan.schedule))
        .where(Loan.member_id == member.id)
        .order_by(Loan.created_at.desc())
    )
    loans = (await db.execute(stmt_loans)).scalars().all()
    total_loans_count = len(loans)
    active_loans_list: list[dict[str, Any]] = []
    total_out_principal = Decimal("0.00")

    for loan in loans:
        figs = await calculate_loan_summary_figures(db, loan)
        if loan.status in [LoanStatus.ACTIVE, LoanStatus.OVERDUE]:
            total_out_principal += figs.outstanding_principal
        active_loans_list.append({
            "loan_id": str(loan.id),
            "loan_number": loan.loan_number,
            "principal": str(loan.principal),
            "status": loan.status.value,
            "disbursed_date": loan.disbursed_at.date().isoformat() if loan.disbursed_at else None,
            "outstanding_principal": str(figs.outstanding_principal),
            "next_due_date": figs.next_due_date.isoformat() if figs.next_due_date else None,
            "next_due_amount": str(figs.next_due_amount),
            "days_overdue": figs.days_overdue,
        })

    # Attendance
    stmt_att = select(Attendance).where(Attendance.member_id == member.id)
    att_records = (await db.execute(stmt_att)).scalars().all()
    total_att = len(att_records)
    present_att = sum(1 for a in att_records if a.status == AttendanceStatus.PRESENT)
    att_rate = quantize_money(Decimal((present_att / total_att) * 100.0)) if total_att > 0 else Decimal("100.00")

    return MemberStatementReportResponse(
        member=MemberStatementSummary(
            member_id=member.id,
            name=member.full_name,
            phone=member.phone,
            shg_name=shg_name,
            status=member.status.value,
            join_date=member.joined_on,
            total_savings_balance=total_savings,
            total_loans_taken=total_loans_count,
            current_outstanding_principal=quantize_money(total_out_principal),
            attendance_rate=att_rate,
        ),
        passbook_entries=passbook_entries,
        active_loans=active_loans_list,
        attendance_summary={
            "total_meetings": total_att,
            "present_count": present_att,
            "attendance_rate": str(att_rate),
        },
    )


async def generate_group_ledger_report(
    db: AsyncSession,
    shg_id: uuid.UUID,
    from_date: date | None = None,
    to_date: date | None = None,
    account_code: str | None = None,
) -> GroupLedgerReportResponse:
    shg = await db.get(SHG, shg_id)
    if not shg:
        raise AppError(code="SHG_NOT_FOUND", message=f"Group {shg_id} not found", status_code=404)

    start = from_date or date(2020, 1, 1)
    end = to_date or date.today()

    # Trial Balance
    stmt_accs = select(Account).where(Account.shg_id == shg_id, Account.is_active.is_(True)).order_by(Account.code.asc())
    if account_code:
        stmt_accs = stmt_accs.where(Account.code.like(f"{account_code}%"))
    accounts = (await db.execute(stmt_accs)).scalars().all()

    # Aggregated line totals per account
    stmt_totals = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0).label("tot_debit"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("tot_credit"),
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(JournalEntry.shg_id == shg_id)
        .group_by(JournalLine.account_id)
    )
    totals_rows = (await db.execute(stmt_totals)).all()
    totals_map = {row[0]: (Decimal(str(row[1])), Decimal(str(row[2]))) for row in totals_rows}

    trial_balance = []
    for a in accounts:
        deb, cred = totals_map.get(a.id, (Decimal("0.00"), Decimal("0.00")))
        net = (deb - cred) if a.type in [AccountType.ASSET, AccountType.EXPENSE] else (cred - deb)
        trial_balance.append({
            "code": a.code,
            "name": a.name,
            "type": a.type.value,
            "debit_balance": str(quantize_money(deb)),
            "credit_balance": str(quantize_money(cred)),
            "net_balance": str(quantize_money(net)),
        })

    # Journal Entries in range
    stmt_entries = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines).selectinload(JournalLine.account))
        .where(
            JournalEntry.shg_id == shg_id,
            JournalEntry.entry_date >= start,
            JournalEntry.entry_date <= end,
        )
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
    )
    entries = (await db.execute(stmt_entries)).scalars().all()

    formatted_entries = []
    for e in entries:
        formatted_entries.append({
            "id": str(e.id),
            "entry_number": f"JE-{str(e.id)[:8]}",
            "entry_date": e.entry_date.isoformat(),
            "description": e.description,
            "lines": [
                {
                    "account_code": line.account.code,
                    "account_name": line.account.name,
                    "debit": str(line.debit),
                    "credit": str(line.credit),
                }
                for line in e.lines
            ],
        })

    return GroupLedgerReportResponse(
        shg_id=shg.id,
        shg_name=shg.name,
        from_date=start,
        to_date=end,
        trial_balance=trial_balance,
        journal_entries=formatted_entries,
    )


async def generate_loan_portfolio_report(
    db: AsyncSession,
    shg_id: uuid.UUID | None = None,
    as_of_date: date | None = None,
) -> LoanPortfolioReportResponse:
    as_of = as_of_date or date.today()

    shg_name = None
    if shg_id:
        shg = await db.get(SHG, shg_id)
        if shg:
            shg_name = shg.name

    metrics = await calculate_portfolio_metrics(db, shg_id=shg_id, as_of_date=as_of)

    # Detailed loans
    query = (
        select(Loan, Member)
        .join(Member, Loan.member_id == Member.id)
        .options(selectinload(Loan.schedule))
        .where(Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE, LoanStatus.CLOSED, LoanStatus.WRITTEN_OFF]))
        .order_by(Loan.created_at.desc())
    )
    if shg_id:
        query = query.where(Loan.shg_id == shg_id)

    loans_res = (await db.execute(query)).all()

    loans_list = []
    buckets_data: dict[str, dict[str, Decimal | int]] = {
        "CURRENT": {"count": 0, "amount": Decimal("0.00")},
        "1-30": {"count": 0, "amount": Decimal("0.00")},
        "31-60": {"count": 0, "amount": Decimal("0.00")},
        "61-90": {"count": 0, "amount": Decimal("0.00")},
        "90+": {"count": 0, "amount": Decimal("0.00")},
    }

    for loan, member in loans_res:
        figs = await calculate_loan_summary_figures(db, loan, as_of_date=as_of)
        days = figs.days_overdue
        out_p = figs.outstanding_principal

        if loan.status in [LoanStatus.ACTIVE, LoanStatus.OVERDUE]:
            if days == 0:
                b_key = "CURRENT"
            elif days <= 30:
                b_key = "1-30"
            elif days <= 60:
                b_key = "31-60"
            elif days <= 90:
                b_key = "61-90"
            else:
                b_key = "90+"
            buckets_data[b_key]["count"] = int(buckets_data[b_key]["count"]) + 1
            buckets_data[b_key]["amount"] = Decimal(str(buckets_data[b_key]["amount"])) + out_p

        loans_list.append({
            "loan_id": str(loan.id),
            "loan_number": loan.loan_number,
            "member_id": str(member.id),
            "member_name": member.full_name,
            "principal": str(loan.principal),
            "status": loan.status.value,
            "disbursed_date": loan.disbursed_at.date().isoformat() if loan.disbursed_at else None,
            "outstanding_principal": str(figs.outstanding_principal),
            "total_interest_due": str(figs.total_interest_due),
            "outstanding_interest": str(figs.outstanding_interest),
            "days_overdue": figs.days_overdue,
            "next_due_date": figs.next_due_date.isoformat() if figs.next_due_date else None,
            "next_due_amount": str(figs.next_due_amount),
        })

    aging_buckets = [
        AgingBucketItem(
            bucket=k,
            count=int(v["count"]),
            amount=quantize_money(Decimal(str(v["amount"]))),
        )
        for k, v in buckets_data.items()
    ]

    metrics_dict = {
        "total_disbursed_principal": str(metrics.total_disbursed_principal),
        "total_principal_repaid": str(metrics.total_principal_repaid),
        "total_outstanding_principal": str(metrics.total_outstanding_principal),
        "total_overdue_principal": str(metrics.total_overdue_principal),
        "active_loans_count": metrics.active_loans_count,
        "overdue_loans_count": metrics.overdue_loans_count,
        "par_30_principal": str(metrics.par_30_principal),
        "par_30_ratio": str(metrics.par_30_ratio),
        "par_60_principal": str(metrics.par_60_principal),
        "par_60_ratio": str(metrics.par_60_ratio),
        "par_90_principal": str(metrics.par_90_principal),
        "par_90_ratio": str(metrics.par_90_ratio),
    }

    return LoanPortfolioReportResponse(
        shg_id=shg_id,
        shg_name=shg_name,
        as_of_date=as_of,
        metrics=metrics_dict,
        aging_buckets=aging_buckets,
        loans=loans_list,
    )


def export_report_to_csv(report_type: str, data: dict[str, Any]) -> str:
    """Exports any report data structure to clean canonical CSV format."""
    output = io.StringIO()
    writer = csv.writer(output)

    if report_type == "group-dashboard":
        writer.writerow(["Group Dashboard Report", data.get("shg_name", ""), str(data.get("as_of_date", ""))])
        writer.writerow([])
        writer.writerow(["Key Figure", "Value"])
        figs = data.get("figures", {})
        writer.writerow(["Total Corpus", figs.get("total_corpus")])
        writer.writerow(["Total Savings", figs.get("total_savings")])
        writer.writerow(["Outstanding Principal", figs.get("outstanding_principal")])
        writer.writerow(["Interest Earned", figs.get("interest_earned")])
        writer.writerow(["Repayment Rate (%)", figs.get("repayment_rate")])
        writer.writerow(["Overdue Amount", figs.get("overdue_amount")])
        writer.writerow(["Next Meeting Date", figs.get("next_meeting_date")])
        writer.writerow(["Collections Due at Next Meeting", figs.get("collections_due_next_meeting")])
        writer.writerow([])

        writer.writerow(["Collections Due List"])
        writer.writerow(["Member Name", "Savings Due", "EMI Due", "Arrears", "Fines", "Total Due"])
        for cd in data.get("collections_due", []):
            writer.writerow([
                cd.get("member_name"),
                cd.get("savings_due"),
                cd.get("emi_due"),
                cd.get("arrears"),
                cd.get("fines"),
                cd.get("total_due"),
            ])
        writer.writerow([])

        writer.writerow(["Savings Trend"])
        writer.writerow(["Month", "Savings Collected"])
        for st in data.get("savings_trend", []):
            writer.writerow([st.get("month"), st.get("amount")])
        writer.writerow([])

        writer.writerow(["Aging Buckets"])
        writer.writerow(["Bucket", "Count", "Outstanding Amount"])
        for ab in data.get("aging_buckets", []):
            writer.writerow([ab.get("bucket"), ab.get("count"), ab.get("amount")])

    elif report_type == "member-statement":
        mem = data.get("member", {})
        writer.writerow(["Member Statement", mem.get("name"), mem.get("shg_name")])
        writer.writerow(["Phone", mem.get("phone", "")])
        writer.writerow(["Status", mem.get("status")])
        writer.writerow(["Join Date", mem.get("join_date")])
        writer.writerow(["Total Savings Balance", mem.get("total_savings_balance")])
        writer.writerow(["Outstanding Principal", mem.get("current_outstanding_principal")])
        writer.writerow(["Attendance Rate (%)", mem.get("attendance_rate")])
        writer.writerow([])

        writer.writerow(["Passbook Ledger Entries"])
        writer.writerow(["Date", "Entry No", "Particulars", "Debit", "Credit", "Balance"])
        for p in data.get("passbook_entries", []):
            writer.writerow([
                p.get("date"),
                p.get("entry_number"),
                p.get("particulars"),
                p.get("debit"),
                p.get("credit"),
                p.get("balance"),
            ])
        writer.writerow([])

        writer.writerow(["Loans"])
        writer.writerow(["Loan No", "Principal", "Status", "Disbursed Date", "Outstanding Principal", "Days Overdue"])
        for loan_item in data.get("active_loans", []):
            writer.writerow([
                loan_item.get("loan_number"),
                loan_item.get("principal"),
                loan_item.get("status"),
                loan_item.get("disbursed_date"),
                loan_item.get("outstanding_principal"),
                loan_item.get("days_overdue"),
            ])

    elif report_type == "group-ledger":
        writer.writerow(["Group Ledger Report", data.get("shg_name", ""), f"{data.get('from_date')} to {data.get('to_date')}"])
        writer.writerow([])
        writer.writerow(["Trial Balance"])
        writer.writerow(["Account Code", "Account Name", "Type", "Debit Balance", "Credit Balance", "Net Balance"])
        for tb in data.get("trial_balance", []):
            writer.writerow([
                tb.get("code"),
                tb.get("name"),
                tb.get("type"),
                tb.get("debit_balance"),
                tb.get("credit_balance"),
                tb.get("net_balance"),
            ])
        writer.writerow([])

        writer.writerow(["Journal Entries"])
        writer.writerow(["Date", "Entry No", "Description", "Account Code", "Account Name", "Debit", "Credit"])
        for e in data.get("journal_entries", []):
            for j_line in e.get("lines", []):
                writer.writerow([
                    e.get("entry_date"),
                    e.get("entry_number"),
                    e.get("description"),
                    j_line.get("account_code"),
                    j_line.get("account_name"),
                    j_line.get("debit"),
                    j_line.get("credit"),
                ])

    elif report_type == "loan-portfolio":
        writer.writerow(["Loan Portfolio Report", data.get("shg_name", "All Groups"), str(data.get("as_of_date", ""))])
        writer.writerow([])
        writer.writerow(["Portfolio Metrics"])
        m = data.get("metrics", {})
        for k, v in m.items():
            writer.writerow([k, v])
        writer.writerow([])

        writer.writerow(["Aging Buckets"])
        writer.writerow(["Bucket", "Loan Count", "Outstanding Principal"])
        for ab in data.get("aging_buckets", []):
            writer.writerow([ab.get("bucket"), ab.get("count"), ab.get("amount")])
        writer.writerow([])

        writer.writerow(["Loans Detail"])
        writer.writerow(["Loan No", "Member Name", "Principal", "Status", "Disbursed Date", "Outstanding Principal", "Days Overdue", "Next Due Date", "Next Due Amount"])
        for loan_row in data.get("loans", []):
            writer.writerow([
                loan_row.get("loan_number"),
                loan_row.get("member_name"),
                loan_row.get("principal"),
                loan_row.get("status"),
                loan_row.get("disbursed_date"),
                loan_row.get("outstanding_principal"),
                loan_row.get("days_overdue"),
                loan_row.get("next_due_date"),
                loan_row.get("next_due_amount"),
            ])

    return output.getvalue()
