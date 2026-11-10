import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.ledger import AccountType, JournalSourceType


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shg_id: uuid.UUID
    code: str
    name: str
    type: AccountType
    member_id: uuid.UUID | None = None
    is_active: bool


class JournalLineResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    account_code: str
    account_name: str
    debit: str
    credit: str


class JournalEntryResponse(BaseModel):
    id: uuid.UUID
    shg_id: uuid.UUID
    entry_date: date
    description: str
    source_type: JournalSourceType
    source_id: uuid.UUID | None = None
    reverses_entry_id: uuid.UUID | None = None
    idempotency_key: str | None = None
    posted_by: uuid.UUID
    posted_at: datetime
    lines: list[JournalLineResponse] = []


class JournalEntryReverseRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500, description="Mandatory audit explanation for reversal")


class PassbookEntryResponse(BaseModel):
    id: uuid.UUID
    entry_id: uuid.UUID
    entry_date: date
    particulars: str
    debit: str
    credit: str
    balance: str
    is_reversal: bool
    reverses_entry_id: uuid.UUID | None = None


class MemberPassbookResponse(BaseModel):
    member_id: uuid.UUID
    member_name: str
    shg_id: uuid.UUID
    total_savings_balance: str
    entries: list[PassbookEntryResponse]


class TrialBalanceItem(BaseModel):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    total_debit: str
    total_credit: str
    net_balance: str


class LedgerReportResponse(BaseModel):
    shg_id: uuid.UUID
    total_debits: str
    total_credits: str
    is_balanced: bool
    trial_balance: list[TrialBalanceItem]
    entries: list[JournalEntryResponse]
