from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class GroupDashboardFigures(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_corpus: Decimal
    total_savings: Decimal
    outstanding_principal: Decimal
    interest_earned: Decimal
    repayment_rate: Decimal
    overdue_amount: Decimal
    next_meeting_date: date | None
    collections_due_next_meeting: Decimal


class SavingsTrendItem(BaseModel):
    month: str
    amount: Decimal


class DisbursalVsRepaymentItem(BaseModel):
    month: str
    disbursed: Decimal
    repaid: Decimal


class AgingBucketItem(BaseModel):
    bucket: str
    count: int
    amount: Decimal


class CollectionDueItem(BaseModel):
    member_id: uuid.UUID
    member_name: str
    savings_due: Decimal
    emi_due: Decimal
    arrears: Decimal
    fines: Decimal
    total_due: Decimal


class GroupDashboardReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shg_id: uuid.UUID
    shg_name: str
    as_of_date: date
    figures: GroupDashboardFigures
    savings_trend: list[SavingsTrendItem]
    disbursals_vs_repayments: list[DisbursalVsRepaymentItem]
    aging_buckets: list[AgingBucketItem]
    collections_due: list[CollectionDueItem]


class MemberStatementSummary(BaseModel):
    member_id: uuid.UUID
    name: str
    phone: str | None
    shg_name: str
    status: str
    join_date: date
    total_savings_balance: Decimal
    total_loans_taken: int
    current_outstanding_principal: Decimal
    attendance_rate: Decimal


class MemberStatementReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    member: MemberStatementSummary
    passbook_entries: list[dict[str, Any]]
    active_loans: list[dict[str, Any]]
    attendance_summary: dict[str, Any]


class GroupLedgerReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shg_id: uuid.UUID
    shg_name: str
    from_date: date
    to_date: date
    trial_balance: list[dict[str, Any]]
    journal_entries: list[dict[str, Any]]


class LoanPortfolioReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shg_id: uuid.UUID | None
    shg_name: str | None
    as_of_date: date
    metrics: dict[str, Any]
    aging_buckets: list[AgingBucketItem]
    loans: list[dict[str, Any]]


class DashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    group_dashboard: GroupDashboardReportResponse | None = None
    member_dashboard: MemberStatementReportResponse | None = None
