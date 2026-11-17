import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DiscrepancyItem(BaseModel):
    shg_id: str
    shg_name: str
    entity_type: str
    entity_id: str
    ledger_value: str
    domain_value: str
    difference: str
    details: str


class ReconciliationRunResponse(BaseModel):
    id: uuid.UUID
    run_at: datetime
    triggered_by: uuid.UUID | None = None
    status: str
    groups_checked_count: int
    discrepancies_count: int
    discrepancies: list[dict[str, Any]]
    execution_time_ms: int
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkerStatusResponse(BaseModel):
    worker_status: str  # "HEALTHY" | "DEGRADED" | "IDLE"
    pending_events_count: int
    processing_events_count: int
    failed_events_count: int
    dead_letter_count: int
    lag_seconds: float
    last_event_processed_at: datetime | None = None
