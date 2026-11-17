from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRequest:
    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    provider: str = ""
    model: str = ""


@dataclass
class LLMStreamChunk:
    delta: str = ""
    tool_call: ToolCallRequest | None = None
    is_done: bool = False


class BaseLLMClient:
    async def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        raise NotImplementedError


class MockLLMClient(BaseLLMClient):
    """Deterministic, offline mock client used when API key is unset or in test evals.
    Inspects queries using rule-based classification to choose tools and generate realistic responses."""

    def __init__(self, model: str = "mock-model") -> None:
        self.model = model

    def _determine_intent(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None
    ) -> tuple[str, list[ToolCallRequest]]:
        last_message = messages[-1]["content"] if messages else ""
        lower = last_message.lower()

        # Check for tool invocations
        tool_calls: list[ToolCallRequest] = []

        # 1. Statement request
        if "statement" in lower or "passbook" in lower:
            import re
            uuid_match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", last_message)
            member_id = uuid_match.group(0) if uuid_match else "m0000000-0000-0000-0000-000000000001"
            tool_calls.append(ToolCallRequest(name="get_member_statement", arguments={"member_id": member_id}))
            return ("Here is the requested member financial statement and recent passbook transactions.", tool_calls)

        # 2. PAR ratio / portfolio (check before overdue so "PAR delinquency" matches get_par_report)
        if "par" in lower or "portfolio" in lower:
            import re
            uuid_match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", last_message)
            shg_id = uuid_match.group(0) if uuid_match else "g0000000-0000-0000-0000-000000000001"
            tool_calls.append(ToolCallRequest(name="get_par_report", arguments={"shg_id": shg_id}))
            return ("Here is the Portfolio At Risk (PAR) and aging analysis for the group.", tool_calls)

        # 3. Overdue loans
        if "overdue" in lower or "delinquen" in lower or "defaul" in lower:
            import re
            uuid_match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", last_message)
            shg_id = uuid_match.group(0) if uuid_match else "g0000000-0000-0000-0000-000000000001"
            tool_calls.append(ToolCallRequest(name="list_overdue", arguments={"shg_id": shg_id}))
            return ("Here are the overdue loans and delinquency details for the group.", tool_calls)

        # 4. Collection sheet
        if "collection sheet" in lower or "meeting dues" in lower or "meeting collections" in lower:
            import re
            uuid_match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", last_message)
            meeting_id = uuid_match.group(0) if uuid_match else "m0000000-0000-0000-0000-000000000001"
            tool_calls.append(ToolCallRequest(name="get_collection_sheet", arguments={"meeting_id": meeting_id}))
            return ("Here is the collection sheet for the scheduled meeting.", tool_calls)

        # 5. Group dashboard / corpus / savings
        if "dashboard" in lower or "corpus" in lower or "savings" in lower or "repayment rate" in lower:
            import re
            uuid_match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", last_message)
            shg_id = uuid_match.group(0) if uuid_match else "g0000000-0000-0000-0000-000000000001"
            tool_calls.append(ToolCallRequest(name="get_group_dashboard", arguments={"shg_id": shg_id}))
            return ("Here is the overall group financial dashboard summary.", tool_calls)

        # Default conversational answer
        return (
            "I am your SHG Credit Assistant. I can help you check group balances, member passbooks, overdue installments, and generate meeting collection drafts.",
            [],
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        content, tool_calls = self._determine_intent(messages, tools)
        return LLMResponse(content=content, tool_calls=tool_calls, provider="mock", model=self.model)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        content, tool_calls = self._determine_intent(messages, tools)
        for tc in tool_calls:
            yield LLMStreamChunk(tool_call=tc)
            await asyncio.sleep(0.01)

        words = content.split(" ")
        for i, word in enumerate(words):
            yield LLMStreamChunk(delta=word + (" " if i < len(words) - 1 else ""))
            await asyncio.sleep(0.01)

        yield LLMStreamChunk(is_done=True)


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini API Provider implementation via REST API."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def _request_with_retries(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/models/{self.model}:{endpoint}?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        for attempt in range(settings.AI_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    return response.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt == settings.AI_MAX_RETRIES:
                    logger.error("Gemini API call failed after retries: %s", str(e))
                    raise
                backoff = 0.5 * (2**attempt)
                await asyncio.sleep(backoff)
        return {}

    async def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        payload: dict[str, Any] = {"contents": contents}
        if tools:
            # Map tools to Gemini function declarations format
            func_decls = [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("parameters", {}),
                }
                for t in tools
            ]
            payload["tools"] = [{"functionDeclarations": func_decls}]

        data = await self._request_with_retries("generateContent", payload)

        candidates = data.get("candidates", [])
        if not candidates:
            return LLMResponse(content="", provider="gemini", model=self.model)

        part = candidates[0].get("content", {}).get("parts", [{}])[0]
        text = part.get("text", "")
        tool_calls: list[ToolCallRequest] = []

        if "functionCall" in part:
            fc = part["functionCall"]
            tool_calls.append(ToolCallRequest(name=fc["name"], arguments=fc.get("args", {})))

        return LLMResponse(content=text, tool_calls=tool_calls, provider="gemini", model=self.model)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        # For simplicity and standard SSE streaming compatibility
        resp = await self.chat(messages, tools)
        for tc in resp.tool_calls:
            yield LLMStreamChunk(tool_call=tc)
        words = resp.content.split(" ")
        for i, word in enumerate(words):
            yield LLMStreamChunk(delta=word + (" " if i < len(words) - 1 else ""))
            await asyncio.sleep(0.01)
        yield LLMStreamChunk(is_done=True)


class OpenAILLMClient(BaseLLMClient):
    """OpenAI API Provider implementation via REST API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.base_url = "https://api.openai.com/v1"

    async def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t.get("parameters", {}),
                    },
                }
                for t in tools
            ]

        for attempt in range(settings.AI_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    choice = data["choices"][0]["message"]
                    content = choice.get("content") or ""
                    tool_calls = []
                    if "tool_calls" in choice and choice["tool_calls"]:
                        for tc in choice["tool_calls"]:
                            fn = tc["function"]
                            args = json.loads(fn.get("arguments", "{}"))
                            tool_calls.append(ToolCallRequest(name=fn["name"], arguments=args, id=tc.get("id", "")))
                    return LLMResponse(content=content, tool_calls=tool_calls, provider="openai", model=self.model)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                if attempt == settings.AI_MAX_RETRIES:
                    logger.error("OpenAI API call failed after retries: %s", str(e))
                    raise
                backoff = 0.5 * (2**attempt)
                await asyncio.sleep(backoff)

        return LLMResponse(content="", provider="openai", model=self.model)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        resp = await self.chat(messages, tools)
        for tc in resp.tool_calls:
            yield LLMStreamChunk(tool_call=tc)
        words = resp.content.split(" ")
        for i, word in enumerate(words):
            yield LLMStreamChunk(delta=word + (" " if i < len(words) - 1 else ""))
            await asyncio.sleep(0.01)
        yield LLMStreamChunk(is_done=True)


def get_llm_client() -> BaseLLMClient:
    """Factory creating configured LLM client with graceful fallback to MockLLMClient
    if API keys are missing or provider is configured to mock."""
    provider = settings.AI_PROVIDER.lower()

    if provider == "gemini" and settings.GEMINI_API_KEY:
        return GeminiLLMClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.AI_MODEL,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )
    elif provider == "openai" and settings.OPENAI_API_KEY:
        return OpenAILLMClient(
            api_key=settings.OPENAI_API_KEY,
            model=settings.AI_MODEL,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )

    # Deterministic mock client for testing, evals, and offline environments
    return MockLLMClient(model=settings.AI_MODEL)
