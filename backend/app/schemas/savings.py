import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.savings import SavingsDueStatus


class SavingsDueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shg_id: uuid.UUID
    member_id: uuid.UUID
    period: str
    amount_due: str
    amount_paid: str
    status: SavingsDueStatus
    member_name: str | None = None


class SavingsDueGenerateRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$", description="Billing period in YYYY-MM format")


class SavingsCollectRequest(BaseModel):
    member_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    fine_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    entry_date: date | None = None
    idempotency_key: str | None = None


class SavingsCollectResponse(BaseModel):
    due: SavingsDueResponse
    new_savings_balance: str
    message: str


class SavingsWithdrawRequest(BaseModel):
    member_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)
    entry_date: date | None = None
    idempotency_key: str | None = None


class SavingsWithdrawResponse(BaseModel):
    member_id: uuid.UUID
    withdrawn_amount: str
    new_savings_balance: str
    message: str
