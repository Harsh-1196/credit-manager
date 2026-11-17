"""
SHG Credit Manager: One-Command Database Reset & Demo Seeding Script (Phase 8)
Usage:
  python scripts/reset_demo_db.py
"""

import asyncio
import os
import sys

# Ensure backend directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
backend_dir = os.path.join(root_dir, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import text
import app.db.models as _models  # noqa: F401 - Ensure all models are registered in Base.metadata
from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal
from app.scripts.seed import seed_data
from app.workers.outbox_worker import process_outbox_batch


async def reset_database() -> None:
    print("=" * 80)
    print("SHG Credit Manager: Resetting Database to Clean Demo State (SPEC Section 16)")
    print("=" * 80)

    # 1. Drop and re-create schema
    print("\n1. Dropping existing tables and rebuilding clean schema...")
    async with engine.begin() as conn:
        # Check dialect
        dialect = conn.dialect.name
        if dialect == "sqlite":
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        else:
            # PostgreSQL cascade drop
            await conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
            await conn.run_sync(Base.metadata.create_all)
    print("   [OK] Clean schema created successfully.")

    # 2. Run full realistic database seed
    print("\n2. Seeding realistic demo data per SPEC Section 16...")
    await seed_data()

    # 3. Process initial outbox events to prime read models
    print("\n3. Priming dashboard read models and outbox events...")
    async with AsyncSessionLocal() as session:
        batch_res = await process_outbox_batch(session, batch_size=200)
        print(f"   [OK] Processed {batch_res.get('published', 0)} outbox events into dashboard read models.")

    print("\n" + "=" * 80)
    print("[SUCCESS] Database has been completely reset to pristine demo state!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(reset_database())
