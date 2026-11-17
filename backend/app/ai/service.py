from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import get_llm_client
from app.ai.schemas import (
    ChatMessage,
    ChatResponse,
    DraftCollectionResponse,
    DraftMemberAmount,
    ToolCallRecord,
    UnmatchedNoteItem,
)
from app.ai.tools import registry, verify_group_access
from app.audit.service import record_audit_log
from app.core.errors import AppError
from app.db.models.auth import User
from app.db.models.meetings import Meeting
from app.db.models.shg import SHG, Member, MemberStatus
from app.services.meetings import get_meeting_collection_sheet


def summarize_tool_result(name: str, result: dict[str, Any]) -> str:
    """Create a concise human-readable summary of the tool result for the UI and audit logs."""
    if result.get("status") == "error":
        return f"Failed: {result.get('error', 'Unknown error')}"

    data = result.get("data", {})
    if name == "get_member_statement":
        return f"Member: {data.get('member_name')}, Savings: ₹{data.get('total_savings_balance')}, Outstanding: ₹{data.get('current_outstanding_principal')}"
    elif name == "list_overdue":
        count = data.get("overdue_count", 0)
        return f"Found {count} overdue loan(s) in group."
    elif name == "get_par_report":
        return f"PAR 30: {data.get('par_30')}, PAR 90: {data.get('par_90')}, Overdue: ₹{data.get('total_overdue_principal')}"
    elif name == "get_group_dashboard":
        return f"Corpus: ₹{data.get('total_corpus')}, Repayment rate: {data.get('repayment_rate')}, Savings: ₹{data.get('total_savings')}"
    elif name == "get_collection_sheet":
        return f"Expected Collections: ₹{data.get('total_expected_collection')} across {data.get('members_count')} members."
    return "Data retrieved successfully."


async def execute_chat(
    messages: list[ChatMessage],
    caller: User,
    db: AsyncSession,
    shg_id: uuid.UUID | None = None,
) -> ChatResponse:
    """Execute AI chat with read-only tools and audit logging."""
    llm = get_llm_client()
    raw_messages = [{"role": m.role, "content": m.content} for m in messages]
    tool_defs = registry.list_definitions()

    initial_resp = await llm.chat(raw_messages, tools=tool_defs)
    tool_records: list[ToolCallRecord] = []

    final_content = initial_resp.content

    if initial_resp.tool_calls:
        # Execute each requested read-only tool
        for tc in initial_resp.tool_calls:
            args = dict(tc.arguments)
            if shg_id and tc.name in ("get_group_dashboard", "list_overdue", "get_par_report"):
                if "shg_id" not in args or args["shg_id"] == "g0000000-0000-0000-0000-000000000001":
                    args["shg_id"] = str(shg_id)

            res = await registry.execute(tc.name, args, db, caller)
            summary = summarize_tool_result(tc.name, res)
            tool_records.append(
                ToolCallRecord(
                    name=tc.name,
                    arguments=args,
                    result_summary=summary,
                    status="success" if res.get("status") == "success" else "error",
                )
            )

        # Generate final assistant response reflecting tool results
        tool_summaries_text = "\n".join([f"[{tr.name}]: {tr.result_summary}" for tr in tool_records])
        updated_messages = list(raw_messages)
        updated_messages.append({"role": "assistant", "content": initial_resp.content or "Let me check that for you."})
        updated_messages.append(
            {
                "role": "system",
                "content": f"The following read-only financial data was retrieved:\n{tool_summaries_text}\nProvide a clear, helpful response based on this data.",
            }
        )

        follow_up = await llm.chat(updated_messages, tools=None)
        final_content = follow_up.content or initial_resp.content

    # Audit log AI interaction (NO PII)
    last_user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")
    await record_audit_log(
        db=db,
        action="AI_CHAT",
        entity_type="AI_ASSISTANT",
        entity_id=uuid.uuid4(),
        actor_id=caller.id,
        actor_role=caller.role.value,
        after={
            "tools_called": [tr.name for tr in tool_records],
            "tool_count": len(tool_records),
            "prompt_length": len(last_user_msg),
            "model": initial_resp.model,
            "provider": initial_resp.provider,
        },
    )

    return ChatResponse(
        content=final_content,
        tool_calls=tool_records,
        provider=initial_resp.provider,
        model=initial_resp.model,
    )


async def stream_chat_events(
    messages: list[ChatMessage],
    caller: User,
    db: AsyncSession,
    shg_id: uuid.UUID | None = None,
) -> AsyncIterator[str]:
    """Stream SSE events for AI chat: tool_start, tool_result, content_delta, done."""
    llm = get_llm_client()
    raw_messages = [{"role": m.role, "content": m.content} for m in messages]
    tool_defs = registry.list_definitions()

    initial_resp = await llm.chat(raw_messages, tools=tool_defs)
    tool_records: list[ToolCallRecord] = []

    # If tools called, execute and stream tool events
    if initial_resp.tool_calls:
        for tc in initial_resp.tool_calls:
            args = dict(tc.arguments)
            if shg_id and tc.name in ("get_group_dashboard", "list_overdue", "get_par_report"):
                if "shg_id" not in args or args["shg_id"] == "g0000000-0000-0000-0000-000000000001":
                    args["shg_id"] = str(shg_id)

            yield f"data: {json.dumps({'type': 'tool_start', 'name': tc.name, 'arguments': args})}\n\n"
            res = await registry.execute(tc.name, args, db, caller)
            summary = summarize_tool_result(tc.name, res)
            rec = ToolCallRecord(
                name=tc.name,
                arguments=args,
                result_summary=summary,
                status="success" if res.get("status") == "success" else "error",
            )
            tool_records.append(rec)
            yield f"data: {json.dumps({'type': 'tool_result', 'name': tc.name, 'summary': summary, 'status': rec.status})}\n\n"

        tool_summaries_text = "\n".join([f"[{tr.name}]: {tr.result_summary}" for tr in tool_records])
        updated_messages = list(raw_messages)
        updated_messages.append({"role": "assistant", "content": initial_resp.content or "Checking data..."})
        updated_messages.append(
            {
                "role": "system",
                "content": f"The following read-only financial data was retrieved:\n{tool_summaries_text}\nProvide a clear, helpful response based on this data.",
            }
        )
        stream_iter = llm.stream_chat(updated_messages, tools=None)
    else:
        stream_iter = llm.stream_chat(raw_messages, tools=None)

    full_content = ""
    async for chunk in stream_iter:
        if chunk.delta:
            full_content += chunk.delta
            yield f"data: {json.dumps({'type': 'content_delta', 'delta': chunk.delta})}\n\n"

    # Audit log
    last_user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")
    await record_audit_log(
        db=db,
        action="AI_CHAT",
        entity_type="AI_ASSISTANT",
        entity_id=uuid.uuid4(),
        actor_id=caller.id,
        actor_role=caller.role.value,
        after={
            "tools_called": [tr.name for tr in tool_records],
            "tool_count": len(tool_records),
            "prompt_length": len(last_user_msg),
            "model": initial_resp.model,
            "provider": initial_resp.provider,
        },
    )

    yield f"data: {json.dumps({'type': 'done', 'tool_calls': [tr.model_dump() for tr in tool_records]})}\n\n"


# -----------------------------------------------------------------------------
# Draft Collection Extraction Engine (Resilient, Pydantic-Validated, Prompt-Injection Safe)
# -----------------------------------------------------------------------------
def sanitize_note_line(line: str) -> str:
    """Strip common prompt-injection delimiters and script tags to ensure prompt-injection safety."""
    cleaned = re.sub(r"(?i)<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", line)
    cleaned = re.sub(r"(?i)system\s*instruction.*?:", "", cleaned)
    cleaned = re.sub(r"(?i)ignore\s+(all\s+)?previous\s+instructions", "", cleaned)
    return cleaned.strip()


async def generate_draft_collection(
    meeting_id: uuid.UUID,
    notes: str,
    caller: User,
    db: AsyncSession,
) -> DraftCollectionResponse:
    """
    Parses unstructured meeting notes (pasted or dictated), maps member dues without guessing,
    flags unmatched and ambiguous names, and returns an uncommitted draft collection payload.
    NEVER writes to the ledger or database tables.
    """
    # 1. Verify meeting and caller access
    m_stmt = select(Meeting).where(Meeting.id == meeting_id)
    m_res = await db.execute(m_stmt)
    meeting = m_res.scalar_one_or_none()
    if not meeting:
        raise AppError(code="NOT_FOUND", message="Resource not found.", status_code=404)

    await verify_group_access(caller, meeting.shg_id, db)

    # Fetch SHG info
    shg_stmt = select(SHG).where(SHG.id == meeting.shg_id)
    shg_res = await db.execute(shg_stmt)
    shg = shg_res.scalar_one()

    # 2. Fetch expected collection sheet dues as reference
    sheet = await get_meeting_collection_sheet(db, meeting_id, meeting.shg_id)
    members_by_id = {m.member_id: m for m in sheet.members}

    # Fetch active member objects for name matching
    mem_stmt = select(Member).where(Member.shg_id == meeting.shg_id, Member.status == MemberStatus.ACTIVE)
    mem_res = await db.execute(mem_stmt)
    active_members = mem_res.scalars().all()

    # 3. Parse notes line by line or sentence by sentence
    raw_lines = [line.strip() for line in re.split(r"[\n;\.]", notes) if line.strip()]

    extracted_items_by_member: dict[uuid.UUID, DraftMemberAmount] = {}
    unmatched_items: list[UnmatchedNoteItem] = []
    ambiguous_members: list[str] = []

    # Pre-populate all active members with expected default dues or 0
    for m in active_members:
        due_info = members_by_id.get(m.id)
        default_savings = Decimal(due_info.savings_due) if due_info else Decimal("0.00")
        default_emi = Decimal(due_info.emi_due) if due_info else Decimal("0.00")
        default_fine = Decimal(due_info.fines_due) if due_info else Decimal("0.00")

        extracted_items_by_member[m.id] = DraftMemberAmount(
            member_id=m.id,
            member_name=m.full_name,
            attendance="PRESENT",
            savings_amount=default_savings,
            loan_repayment_amount=default_emi,
            fine_amount=default_fine,
            total_amount=default_savings + default_emi + default_fine,
            confidence=0.5,  # Baseline expected dues
            notes="Default from collection sheet",
        )

    for line in raw_lines:
        clean_line = sanitize_note_line(line)
        if not clean_line:
            continue

        lower = clean_line.lower()

        # Check for absent cue
        is_absent = any(w in lower for w in ["absent", "gairhazir", "not present", "couldn't attend", "nahi aayi"])

        # Extract potential amounts (e.g., 500, 1100, 50, ₹1000)
        amount_matches = re.findall(r"₹?\s*(\d+(?:\.\d{1,2})?)", clean_line)
        detected_amounts = [Decimal(a) for a in amount_matches]

        # Name candidate extraction: find matching active member
        # Split tokens
        candidate_matches: list[Member] = []
        for m in active_members:
            m_name_lower = m.full_name.lower()
            first_name = m_name_lower.split()[0]
            last_name = m_name_lower.split()[-1] if len(m_name_lower.split()) > 1 else ""

            # Check full name or first name boundary
            if re.search(rf"\b{re.escape(m_name_lower)}\b", lower):
                candidate_matches.append(m)
            elif re.search(rf"\b{re.escape(first_name)}\b", lower):
                candidate_matches.append(m)
            elif last_name and len(last_name) > 3 and re.search(rf"\b{re.escape(last_name)}\b", lower):
                candidate_matches.append(m)

        # De-duplicate candidate matches
        candidate_matches = list({m.id: m for m in candidate_matches}.values())

        if len(candidate_matches) == 1:
            matched_member = candidate_matches[0]
            existing = extracted_items_by_member[matched_member.id]

            if is_absent:
                existing.attendance = "ABSENT"
                existing.savings_amount = Decimal("0.00")
                existing.loan_repayment_amount = Decimal("0.00")
                existing.fine_amount = Decimal("0.00")
                existing.total_amount = Decimal("0.00")
                existing.confidence = 1.0
                existing.notes = "Marked absent from meeting notes"
            elif detected_amounts:
                # If specific keywords are present
                has_savings_kw = any(w in lower for w in ["saving", "bachat", "deposit", "dues"])
                has_emi_kw = any(w in lower for w in ["emi", "loan", "kist", "installment"])
                has_fine_kw = any(w in lower for w in ["fine", "penalty", "dand", "late"])

                if len(detected_amounts) == 1:
                    amt = detected_amounts[0]
                    if has_fine_kw:
                        existing.fine_amount = amt
                    elif has_emi_kw:
                        existing.loan_repayment_amount = amt
                    elif has_savings_kw or amt <= 1000:
                        existing.savings_amount = amt
                    else:
                        # Ambiguous single amount: assign to loan if loan due, else savings
                        existing.loan_repayment_amount = amt
                elif len(detected_amounts) >= 2:
                    # Multiple amounts: typically [savings, emi] or [savings, fine]
                    if has_fine_kw:
                        existing.savings_amount = detected_amounts[0]
                        existing.fine_amount = detected_amounts[1]
                    else:
                        existing.savings_amount = detected_amounts[0]
                        existing.loan_repayment_amount = detected_amounts[1]

                existing.total_amount = existing.savings_amount + existing.loan_repayment_amount + existing.fine_amount
                existing.confidence = 0.95
                existing.notes = f"Parsed from: '{clean_line}'"

        elif len(candidate_matches) > 1:
            # Ambiguous match: multiple members match the name!
            names = [m.full_name for m in candidate_matches]
            unmatched_items.append(
                UnmatchedNoteItem(
                    raw_text=clean_line,
                    reason="AMBIGUOUS_MATCH",
                    candidate_names=names,
                    detected_amount=detected_amounts[0] if detected_amounts else None,
                )
            )
            for n in names:
                if n not in ambiguous_members:
                    ambiguous_members.append(n)
        else:
            # Unmatched candidate
            # If line mentions amounts or payments but no member matched
            if detected_amounts or is_absent:
                unmatched_items.append(
                    UnmatchedNoteItem(
                        raw_text=clean_line,
                        reason="UNMATCHED_MEMBER",
                        candidate_names=[],
                        detected_amount=detected_amounts[0] if detected_amounts else None,
                    )
                )

    items_list = list(extracted_items_by_member.values())
    total_draft = sum((item.total_amount for item in items_list), Decimal("0.00"))

    # Audit log (NO PII)
    await record_audit_log(
        db=db,
        action="AI_DRAFT_COLLECTION",
        entity_type="AI_ASSISTANT",
        entity_id=meeting_id,
        actor_id=caller.id,
        actor_role=caller.role.value,
        after={
            "meeting_id": str(meeting_id),
            "members_matched_count": len(items_list),
            "unmatched_count": len(unmatched_items),
            "ambiguous_count": len(ambiguous_members),
            "total_draft": str(total_draft),
            "notes_length": len(notes),
        },
    )

    return DraftCollectionResponse(
        meeting_id=meeting.id,
        shg_id=shg.id,
        shg_name=shg.name,
        meeting_date=meeting.meeting_date,
        items=items_list,
        unmatched_items=unmatched_items,
        ambiguous_members=ambiguous_members,
        total_collected_draft=total_draft,
    )
