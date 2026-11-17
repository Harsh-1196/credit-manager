from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import ChatRequest, ChatResponse, DraftCollectionRequest, DraftCollectionResponse
from app.ai.service import execute_chat, generate_draft_collection, stream_chat_events
from app.api.deps import get_current_user, get_db
from app.db.models.auth import User

router = APIRouter()


@router.post(
    "/chat",
    response_model=None,
    summary="Interactive AI Assistant with Read-Only Financial Tools",
)
async def ai_chat(
    req: ChatRequest,
    accept: str | None = Header(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse | ChatResponse:
    """
    AI Assistant chat endpoint.
    If 'text/event-stream' is requested (default for chat UI), streams SSE events:
    - tool_start: tool execution initiated
    - tool_result: structured tool response summary
    - content_delta: streamed assistant text tokens
    - done: final completion with complete tool calls list
    If 'application/json' is explicitly accepted, returns complete ChatResponse JSON.
    """
    if accept and "application/json" in accept and "text/event-stream" not in accept:
        return await execute_chat(
            messages=req.messages,
            caller=current_user,
            db=db,
            shg_id=req.shg_id,
        )

    # Return SSE streaming response
    return StreamingResponse(
        stream_chat_events(
            messages=req.messages,
            caller=current_user,
            db=db,
            shg_id=req.shg_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/draft-collection",
    response_model=DraftCollectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract Draft Meeting Collections from Notes",
)
async def ai_draft_collection(
    req: DraftCollectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DraftCollectionResponse:
    """
    Takes unstructured or dictated meeting notes, maps per-member amounts,
    flags unmatched and ambiguous names, and returns a verified draft collection payload.
    It is strictly a draft; no data is posted to the database or double-entry ledger.
    """
    return await generate_draft_collection(
        meeting_id=req.meeting_id,
        notes=req.notes,
        caller=current_user,
        db=db,
    )
