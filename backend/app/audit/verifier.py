import asyncio
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import compute_row_hash, format_audit_dt
from app.db.models.platform import AuditLog
from app.db.session import AsyncSessionLocal


async def verify_audit_chain(db: AsyncSession) -> dict[str, Any]:
    """
    Verifies the integrity of the cryptographic hash chain across all audit log rows.
    Returns dictionary with:
        valid: bool
        count: int
        broken_at_index: int | None
        broken_at_id: str | None
        error: str | None
        message: str
    """
    stmt = select(AuditLog).order_by(AuditLog.occurred_at.asc(), AuditLog.created_at.asc())
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    if not rows:
        return {"valid": True, "count": 0, "error": None, "message": "Audit chain is empty and intact."}

    current_prev_hash: str | None = None

    for idx, row in enumerate(rows):
        # 1. Verify prev_hash matches previous row_hash
        if row.prev_hash != current_prev_hash:
            return {
                "valid": False,
                "count": idx,
                "broken_at_index": idx,
                "broken_at_id": str(row.id),
                "error": f"Previous hash link broken at index {idx}",
                "expected_prev_hash": current_prev_hash,
                "found_prev_hash": row.prev_hash,
                "message": f"Broken chain link at row {idx} (ID: {row.id})",
            }

        # 2. Recompute row_hash from canonical payload
        payload = {
            "action": row.action,
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "actor_role": row.actor_role,
            "after": row.after,
            "before": row.before,
            "entity_id": str(row.entity_id),
            "entity_type": row.entity_type,
            "ip": row.ip,
            "occurred_at": format_audit_dt(row.occurred_at),
            "request_id": row.request_id,
            "user_agent": row.user_agent,
        }
        recomputed_hash = compute_row_hash(current_prev_hash, payload)

        if row.row_hash != recomputed_hash:
            return {
                "valid": False,
                "count": idx,
                "broken_at_index": idx,
                "broken_at_id": str(row.id),
                "error": f"Tampered row at index {idx}",
                "expected_row_hash": recomputed_hash,
                "found_row_hash": row.row_hash,
                "message": f"Content tampering detected at index {idx} (ID: {row.id})",
            }

        current_prev_hash = row.row_hash

    return {
        "valid": True,
        "count": len(rows),
        "error": None,
        "message": f"Audit chain verified successfully across {len(rows)} entries.",
    }


async def run_cli() -> None:
    print("Verifying audit log tamper-evident hash chain...")
    async with AsyncSessionLocal() as session:
        res = await verify_audit_chain(session)
        if res["valid"]:
            print(f"[OK] Audit log chain verified successfully ({res['count']} entries).")
            sys.exit(0)
        else:
            print(f"[FAIL] Audit log verification failed: {res['error']} - {res['message']}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_cli())
