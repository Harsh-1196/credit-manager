from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    shg_id: uuid.UUID | None = None


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict[str, Any]
    result_summary: str
    status: Literal["success", "error"]


class ChatResponse(BaseModel):
    content: str
    tool_calls: list[ToolCallRecord]
    provider: str
    model: str


class DraftMemberAmount(BaseModel):
    member_id: uuid.UUID
    member_name: str
    attendance: Literal["PRESENT", "ABSENT", "EXCUSED"] = "PRESENT"
    savings_amount: Decimal = Decimal("0.00")
    loan_repayment_amount: Decimal = Decimal("0.00")
    fine_amount: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    confidence: float = 1.0
    notes: str | None = None


class UnmatchedNoteItem(BaseModel):
    raw_text: str
    reason: Literal["UNMATCHED_MEMBER", "AMBIGUOUS_MATCH", "UNPARSED_AMOUNT"]
    candidate_names: list[str] = Field(default_factory=list)
    detected_amount: Decimal | None = None


class DraftCollectionRequest(BaseModel):
    meeting_id: uuid.UUID
    notes: str


class DraftCollectionResponse(BaseModel):
    meeting_id: uuid.UUID
    shg_id: uuid.UUID
    shg_name: str
    meeting_date: date
    items: list[DraftMemberAmount]
    unmatched_items: list[UnmatchedNoteItem] = Field(default_factory=list)
    ambiguous_members: list[str] = Field(default_factory=list)
    total_collected_draft: Decimal
    disclaimer: str = (
        "This is an uncommitted AI draft generated from notes. Review all rows and click 'Confirm & Post' to commit."
    )
