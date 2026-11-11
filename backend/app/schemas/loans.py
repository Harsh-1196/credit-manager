import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.loans import LoanScheduleStatus, LoanStatus
from app.db.models.shg import InterestType


class EligibilityCheckItemResponse(BaseModel):
    code: str
    name: str
    passed: bool
    severity: str
    message: str
    actual_value: str | None = None
    threshold_value: str | None = None


class EligibilityResponse(BaseModel):
    is_eligible: bool
    has_warnings: bool
    summary_message: str
    checks: list[EligibilityCheckItemResponse]


class LoanScheduleItemResponse(BaseModel):
    installment_no: int
    due_date: date
    principal_due: str
    interest_due: str
    total_due: str
    outstanding_balance: str = "0.00"
    principal_paid: str = "0.00"
    interest_paid: str = "0.00"
    penalty_paid: str = "0.00"
    penalty_due: str = "0.00"
    status: LoanScheduleStatus = LoanScheduleStatus.PENDING
    days_overdue: int = 0


class LoanPreviewScheduleRequest(BaseModel):
    shg_id: uuid.UUID
    member_id: uuid.UUID | None = None
    principal: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    annual_rate: Decimal = Field(ge=0, max_digits=6, decimal_places=3)
    interest_type: InterestType = InterestType.REDUCING
    tenure_months: int = Field(ge=1, le=120)
    first_due_date: date


class LoanPreviewScheduleResponse(BaseModel):
    principal: str
    total_interest: str
    total_amount: str
    monthly_installment: str
    installments: list[LoanScheduleItemResponse]
    eligibility: EligibilityResponse | None = None


class LoanCreateRequest(BaseModel):
    shg_id: uuid.UUID
    member_id: uuid.UUID
    purpose: str = Field(min_length=3, max_length=500)
    principal: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    interest_rate: Decimal = Field(ge=0, max_digits=6, decimal_places=3)
    interest_type: InterestType = InterestType.REDUCING
    tenure_months: int = Field(ge=1, le=120)
    first_due_date: date
    submit_immediately: bool = False


class LoanApproveRequest(BaseModel):
    version: int = Field(description="Optimistic locking expected version")
    reason: str | None = Field(default=None, max_length=500)


class LoanRejectRequest(BaseModel):
    version: int = Field(description="Optimistic locking expected version")
    reason: str = Field(min_length=3, max_length=500, description="Mandatory rejection explanation")


class LoanDisburseRequest(BaseModel):
    version: int = Field(description="Optimistic locking expected version")
    first_due_date: date | None = None
    idempotency_key: str | None = None


class DisburseJournalLine(BaseModel):
    account_code: str
    account_name: str
    debit: str
    credit: str


class LoanDisbursePreviewResponse(BaseModel):
    loan_id: uuid.UUID
    loan_number: str
    member_name: str
    principal: str
    processing_fee: str
    net_disbursed: str
    group_cash_balance: str
    has_sufficient_cash: bool
    journal_lines: list[DisburseJournalLine]


class LoanRepayRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    payment_date: date | None = None
    version: int | None = None
    idempotency_key: str | None = None


class LoanRepayPreviewRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    payment_date: date | None = None


class RepayInstallmentEffect(BaseModel):
    installment_no: int
    due_date: str
    penalty_allocated: str
    interest_allocated: str
    principal_allocated: str
    total_allocated: str
    status_before: str
    status_after: str


class LoanRepayPreviewResponse(BaseModel):
    loan_id: uuid.UUID
    loan_number: str
    payment_amount: str
    penalty_allocated: str
    interest_allocated: str
    principal_allocated: str
    prepayment_principal: str
    is_loan_fully_paid: bool
    remaining_principal_after: str
    installments_affected: list[RepayInstallmentEffect]


class LoanWriteOffRequest(BaseModel):
    version: int = Field(description="Optimistic locking expected version")
    reason: str = Field(min_length=3, max_length=500, description="Mandatory write-off justification")


class LoanSummaryFiguresResponse(BaseModel):
    outstanding_principal: str
    outstanding_interest: str
    outstanding_penalty: str
    total_outstanding_balance: str
    total_principal_paid: str
    total_interest_paid: str
    total_penalty_paid: str
    next_due_date: date | None
    next_due_amount: str
    days_overdue: int


class LoanStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_id: uuid.UUID
    from_status: LoanStatus
    to_status: LoanStatus
    actor_id: uuid.UUID
    reason: str | None = None
    created_at: datetime


class LoanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shg_id: uuid.UUID
    member_id: uuid.UUID
    member_name: str | None = None
    loan_number: str
    purpose: str
    principal: str
    interest_rate: str
    interest_type: InterestType
    tenure_months: int
    processing_fee: str
    status: LoanStatus
    applied_by: uuid.UUID
    applied_at: datetime | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    disbursed_at: datetime | None = None
    disbursed_by: uuid.UUID | None = None
    first_due_date: date | None = None
    closed_at: datetime | None = None
    written_off_at: datetime | None = None
    written_off_by: uuid.UUID | None = None
    write_off_reason: str | None = None
    version: int
    created_at: datetime
    can_approve: bool = False
    maker_checker_note: str | None = None


class LoanDetailResponse(LoanResponse):
    schedule: list[LoanScheduleItemResponse] = []
    history: list[LoanStatusHistoryResponse] = []
    eligibility: EligibilityResponse | None = None
    summary: LoanSummaryFiguresResponse | None = None


class PortfolioMetricsResponse(BaseModel):
    shg_id: uuid.UUID | None = None
    as_of_date: date
    total_loans_count: int
    active_loans_count: int
    overdue_loans_count: int
    closed_loans_count: int
    written_off_loans_count: int
    total_disbursed_principal: str
    total_principal_repaid: str
    total_outstanding_principal: str
    total_overdue_principal: str
    total_interest_outstanding: str
    total_penalty_outstanding: str
    par_30_principal: str
    par_30_count: int
    par_30_ratio: str
    par_60_principal: str
    par_60_count: int
    par_60_ratio: str
    par_90_principal: str
    par_90_count: int
    par_90_ratio: str
