import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class ReconciliationStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    DISCREPANCIES_FOUND = "DISCREPANCIES_FOUND"
    FAILED = "FAILED"


class ReconciliationRun(Base):
    """
    Stores audit and reconciliation execution runs comparing double-entry ledger lines
    against domain state and denormalized dashboard read models.
    """

    __tablename__ = "reconciliation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, native_enum=False),
        nullable=False,
        default=ReconciliationStatus.COMPLETED,
    )
    groups_checked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discrepancies_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discrepancies: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    execution_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
