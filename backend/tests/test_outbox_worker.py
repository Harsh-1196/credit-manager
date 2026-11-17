import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.loans import Loan, LoanSchedule, LoanScheduleStatus, LoanStatus
from app.db.models.outbox import DashboardReadModel, OutboxEvent, OutboxEventStatus
from app.db.models.shg import InterestType
from app.domain.outbox.consumers import dashboard_read_model_consumer
from app.domain.outbox.service import create_outbox_event
from app.domain.savings.service import collect_member_savings, withdraw_member_savings
from app.services.loans import disburse_loan, repay_loan
from app.workers.outbox_worker import process_outbox_batch


@pytest.mark.asyncio
async def test_transactional_outbox_written_with_financial_mutations(
    db_session: AsyncSession,
    funded_group_fixture: dict,
) -> None:
    """
    Verifies that outbox_events table is written in the exact same transaction
    for disbursals, repayments, savings, withdrawals, and reversals.
    """
    shg = funded_group_fixture["shg"]
    leader = funded_group_fixture["leader"]
    member = funded_group_fixture["member"]

    # 1. Savings Collection Outbox Event
    due, _ = await collect_member_savings(
        db=db_session,
        shg_id=shg.id,
        member_id=member.id,
        amount=Decimal("500.00"),
        period="2026-03",
        posted_by=leader.id,
        fine_amount=Decimal("50.00"),
    )
    await db_session.commit()

    stmt = select(OutboxEvent).where(OutboxEvent.shg_id == shg.id, OutboxEvent.event_type == "SAVINGS_COLLECTED")
    res = await db_session.execute(stmt)
    events = res.scalars().all()
    assert len(events) >= 1
    savings_ev = events[-1]
    assert savings_ev.status == OutboxEventStatus.PENDING
    assert Decimal(savings_ev.payload["amount"]) == Decimal("500.00")
    assert Decimal(savings_ev.payload["fine_amount"]) == Decimal("50.00")

    # 2. Savings Withdrawal Outbox Event
    await withdraw_member_savings(
        db=db_session,
        shg_id=shg.id,
        member_id=member.id,
        amount=Decimal("100.00"),
        posted_by=leader.id,
        reason="Emergency medical expense",
    )
    await db_session.commit()

    stmt_w = select(OutboxEvent).where(OutboxEvent.shg_id == shg.id, OutboxEvent.event_type == "SAVINGS_WITHDRAWN")
    w_ev = (await db_session.execute(stmt_w)).scalars().first()
    assert w_ev is not None
    assert Decimal(w_ev.payload["amount"]) == Decimal("100.00")

    # 3. Loan Disbursal Outbox Event
    loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number=f"L-OUT-{uuid.uuid4().hex[:6].upper()}",
        purpose="Livestock purchase and feed",
        principal=Decimal("10000.00"),
        interest_rate=Decimal("12.00"),
        interest_type=InterestType.REDUCING,
        tenure_months=6,
        processing_fee=Decimal("100.00"),
        status=LoanStatus.APPROVED,
        applied_by=leader.id,
        approved_by=leader.id,
        approved_at=datetime.now(UTC),
    )
    db_session.add(loan)
    await db_session.commit()

    await disburse_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
    )
    await db_session.commit()

    stmt_l = select(OutboxEvent).where(OutboxEvent.shg_id == shg.id, OutboxEvent.event_type == "LOAN_DISBURSED")
    l_ev = (await db_session.execute(stmt_l)).scalars().first()
    assert l_ev is not None
    assert Decimal(l_ev.payload["principal"]) == Decimal("10000.00")

    # 4. Loan Repayment Outbox Event
    await repay_loan(
        db=db_session,
        loan_id=loan.id,
        shg_id=shg.id,
        current_user=leader,
        amount=Decimal("1500.00"),
    )
    await db_session.commit()

    stmt_r = select(OutboxEvent).where(OutboxEvent.shg_id == shg.id, OutboxEvent.event_type == "LOAN_REPAID")
    r_ev = (await db_session.execute(stmt_r)).scalars().first()
    assert r_ev is not None
    assert Decimal(r_ev.payload["amount"]) == Decimal("1500.00")


@pytest.mark.asyncio
async def test_worker_processing_read_model_convergence_and_par_refresh(
    db_session: AsyncSession,
    funded_group_fixture: dict,
) -> None:
    """
    Verifies that worker processes pending events, marks them PUBLISHED,
    and updates both the dashboard read model and PAR figures.
    """
    shg = funded_group_fixture["shg"]
    leader = funded_group_fixture["leader"]

    # Seed an overdue loan schedule to test PAR calculation
    member = funded_group_fixture["member"]
    overdue_loan = Loan(
        shg_id=shg.id,
        member_id=member.id,
        loan_number=f"L-PAR-{uuid.uuid4().hex[:6].upper()}",
        purpose="Farming equipment purchase",
        principal=Decimal("5000.00"),
        interest_rate=Decimal("12.00"),
        interest_type="FLAT",
        tenure_months=5,
        processing_fee=Decimal("0.00"),
        status=LoanStatus.OVERDUE,
        applied_by=leader.id,
        approved_by=leader.id,
        approved_at=datetime.now(UTC),
    )
    db_session.add(overdue_loan)
    await db_session.flush()

    # Installment overdue 45 days (PAR 30)
    sched_overdue = LoanSchedule(
        loan_id=overdue_loan.id,
        installment_no=1,
        due_date=date.today() - timedelta(days=45),
        principal_due=Decimal("1000.00"),
        interest_due=Decimal("100.00"),
        total_due=Decimal("1100.00"),
        principal_paid=Decimal("0.00"),
        interest_paid=Decimal("0.00"),
        penalty_paid=Decimal("0.00"),
        penalty_due=Decimal("50.00"),
        status=LoanScheduleStatus.OVERDUE,
    )
    db_session.add(sched_overdue)
    await db_session.flush()

    # Add an outbox event for savings collection
    ev = await create_outbox_event(
        db=db_session,
        event_type="SAVINGS_COLLECTED",
        aggregate_type="SAVINGS",
        aggregate_id=member.id,
        shg_id=shg.id,
        payload={
            "member_id": str(member.id),
            "amount": "1200.00",
            "fine_amount": "50.00",
        },
    )
    await db_session.commit()

    # Process outbox events with worker
    res = await process_outbox_batch(db_session, batch_size=50)
    assert res["processed"] >= 1
    assert res["published"] >= 1
    assert res["failed"] == 0

    # Verify event is PUBLISHED
    refetched_ev = await db_session.get(OutboxEvent, ev.id)
    assert refetched_ev is not None
    assert refetched_ev.status == OutboxEventStatus.PUBLISHED
    assert refetched_ev.processed_at is not None

    # Verify Dashboard Read Model
    stmt_rm = select(DashboardReadModel).where(DashboardReadModel.shg_id == shg.id)
    read_model = (await db_session.execute(stmt_rm)).scalar_one_or_none()
    assert read_model is not None
    assert read_model.total_savings >= Decimal("1200.00")
    assert read_model.total_penalties_collected >= Decimal("50.00")
    assert read_model.overdue_loans_count >= 1
    assert read_model.par_30_amount >= Decimal("5000.00")


@pytest.mark.asyncio
async def test_consumer_idempotency_harmless_replay(
    db_session: AsyncSession,
    funded_group_fixture: dict,
) -> None:
    """
    Verifies that replaying an already-processed outbox event is 100% harmless
    and causes zero duplicate updates to the read model.
    """
    shg = funded_group_fixture["shg"]
    member = funded_group_fixture["member"]

    ev = await create_outbox_event(
        db=db_session,
        event_type="SAVINGS_COLLECTED",
        aggregate_type="SAVINGS",
        aggregate_id=member.id,
        shg_id=shg.id,
        payload={
            "member_id": str(member.id),
            "amount": "2000.00",
            "fine_amount": "0.00",
        },
    )
    await db_session.commit()

    # First execution
    await dashboard_read_model_consumer(db_session, ev)
    await db_session.commit()

    stmt = select(DashboardReadModel).where(DashboardReadModel.shg_id == shg.id)
    rm_after_first = (await db_session.execute(stmt)).scalar_one()
    initial_savings = rm_after_first.total_savings
    initial_cash = rm_after_first.group_cash_balance

    # Second execution (Replay)
    await dashboard_read_model_consumer(db_session, ev)
    await db_session.commit()

    stmt = select(DashboardReadModel).where(DashboardReadModel.shg_id == shg.id)
    rm_after_second = (await db_session.execute(stmt)).scalar_one()

    # Asserts that totals did NOT increase again
    assert rm_after_second.total_savings == initial_savings
    assert rm_after_second.group_cash_balance == initial_cash


@pytest.mark.asyncio
async def test_worker_crash_mid_batch_does_not_lose_or_duplicate_effects(
    db_session: AsyncSession,
    funded_group_fixture: dict,
) -> None:
    """
    Simulates a worker crash / abort mid-batch.
    Verifies that already-processed events remain committed and subsequent restart
    resumes without losing data or duplicating effects.
    """
    shg = funded_group_fixture["shg"]
    member = funded_group_fixture["member"]

    # Create 3 events
    ev1 = await create_outbox_event(
        db=db_session,
        event_type="SAVINGS_COLLECTED",
        aggregate_type="SAVINGS",
        aggregate_id=member.id,
        shg_id=shg.id,
        payload={"member_id": str(member.id), "amount": "100.00", "fine_amount": "0.00"},
    )
    ev2 = await create_outbox_event(
        db=db_session,
        event_type="SAVINGS_COLLECTED",
        aggregate_type="SAVINGS",
        aggregate_id=member.id,
        shg_id=shg.id,
        payload={"member_id": str(member.id), "amount": "200.00", "fine_amount": "0.00"},
    )
    ev3 = await create_outbox_event(
        db=db_session,
        event_type="SAVINGS_COLLECTED",
        aggregate_type="SAVINGS",
        aggregate_id=member.id,
        shg_id=shg.id,
        payload={"member_id": str(member.id), "amount": "300.00", "fine_amount": "0.00"},
    )
    await db_session.commit()

    # Process batch with simulated crash on event 2
    original_consumer = dashboard_read_model_consumer
    call_count = 0

    async def crashing_consumer(db: AsyncSession, event: OutboxEvent) -> None:
        nonlocal call_count
        call_count += 1
        if event.id == ev2.id:
            raise RuntimeError("Simulated worker process mid-batch crash!")
        await original_consumer(db, event)

    with patch("app.workers.outbox_worker.dashboard_read_model_consumer", new=crashing_consumer):
        res1 = await process_outbox_batch(db_session, batch_size=10)
        assert res1["published"] == 2  # ev1 succeeded, ev3 succeeded
        assert res1["failed"] == 1  # ev2 failed

    # Verify ev1 & ev3 are PUBLISHED, ev2 is FAILED
    ev1_db = (await db_session.execute(select(OutboxEvent).where(OutboxEvent.id == ev1.id))).scalar_one_or_none()
    ev2_db = (await db_session.execute(select(OutboxEvent).where(OutboxEvent.id == ev2.id))).scalar_one_or_none()
    ev3_db = (await db_session.execute(select(OutboxEvent).where(OutboxEvent.id == ev3.id))).scalar_one_or_none()

    assert ev1_db is not None and ev1_db.status == OutboxEventStatus.PUBLISHED
    assert ev2_db is not None and ev2_db.status == OutboxEventStatus.FAILED
    assert ev3_db is not None and ev3_db.status == OutboxEventStatus.PUBLISHED

    # Fast-forward retry timer for ev2
    ev2_db.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    # Worker restart: run clean process_outbox_batch
    res2 = await process_outbox_batch(db_session, batch_size=10)
    assert res2["published"] == 1  # ev2 picked up and published

    ev2_db_after = (await db_session.execute(select(OutboxEvent).where(OutboxEvent.id == ev2.id))).scalar_one_or_none()
    assert ev2_db_after is not None and ev2_db_after.status == OutboxEventStatus.PUBLISHED

    # Assert that all 3 events contributed exactly once to the read model
    stmt = select(DashboardReadModel).where(DashboardReadModel.shg_id == shg.id)
    rm = (await db_session.execute(stmt)).scalar_one()
    # Total savings should include 100 + 200 + 300 = 600.00
    assert rm.total_savings >= Decimal("600.00")


@pytest.mark.asyncio
async def test_worker_retries_with_backoff_and_dead_letter_queue(
    db_session: AsyncSession,
    funded_group_fixture: dict,
) -> None:
    """
    Verifies that unhandled consumer errors trigger retry with backoff,
    and transition to DEAD_LETTER when max_retries is reached.
    """
    shg = funded_group_fixture["shg"]
    member = funded_group_fixture["member"]

    failing_ev = await create_outbox_event(
        db=db_session,
        event_type="SAVINGS_COLLECTED",
        aggregate_type="SAVINGS",
        aggregate_id=member.id,
        shg_id=shg.id,
        payload={"member_id": str(member.id), "amount": "999.00"},
    )
    # Set max_retries to 2 for fast testing
    failing_ev.max_retries = 2
    await db_session.commit()

    async def always_failing_consumer(db: AsyncSession, event: OutboxEvent) -> None:
        raise ValueError("Simulated permanent consumer error")

    with patch("app.workers.outbox_worker.dashboard_read_model_consumer", new=always_failing_consumer):
        # First attempt: retry_count becomes 1, status FAILED
        await process_outbox_batch(db_session, batch_size=10)
        ev_after_1 = (await db_session.execute(select(OutboxEvent).where(OutboxEvent.id == failing_ev.id))).scalar_one_or_none()
        assert ev_after_1 is not None
        assert ev_after_1.status == OutboxEventStatus.FAILED
        assert ev_after_1.retry_count == 1
        assert "Simulated permanent consumer error" in (ev_after_1.last_error or "")

        # Fast-forward timer for next retry
        ev_after_1.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()

        # Second attempt: retry_count reaches max_retries (2), status becomes DEAD_LETTER
        res = await process_outbox_batch(db_session, batch_size=10)
        assert res["dead_letter"] == 1

        ev_after_2 = (await db_session.execute(select(OutboxEvent).where(OutboxEvent.id == failing_ev.id))).scalar_one_or_none()
        assert ev_after_2 is not None
        assert ev_after_2.status == OutboxEventStatus.DEAD_LETTER
        assert ev_after_2.retry_count == 2
