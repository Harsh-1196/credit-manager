from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.evals import run_all_evals


@pytest.mark.asyncio
async def test_ai_benchmark_and_eval_suite_100_percent_pass(db_session: AsyncSession):
    """Executes the full 16-case benchmark fixture suite testing tool choices,
    draft collection amounts extraction, scope isolation, and prompt injection safety."""
    eval_output = await run_all_evals(db_session)
    assert eval_output["total_cases"] >= 15
    assert eval_output["passed_count"] == eval_output["total_cases"]
    assert eval_output["pass_rate"] == 100.0
