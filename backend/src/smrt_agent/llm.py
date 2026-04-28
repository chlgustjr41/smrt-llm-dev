"""Unified LLM client: Anthropic and OpenAI-compatible (LM Studio) backends.

All agent loops use this module. Messages are always kept in Anthropic canonical
format; the client converts to OpenAI format internally when `use_local` is True.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from smrt_agent.settings import Settings


# ── Normalized response types ─────────────────────────────────────────────


@dataclass
class NormalizedToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class NormalizedTextBlock:
    text: str


@dataclass
class NormalizedResponse:
    stop_reason: str  # "end_turn" or "tool_use"
    blocks: list[NormalizedToolUse | NormalizedTextBlock] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


# ── Tool definition converters ────────────────────────────────────────────


def _anthropic_tool_to_openai(tool: dict) -> dict:
    """Convert Anthropic tool definition to OpenAI function format."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


# ── Message format converters ─────────────────────────────────────────────


def _anthropic_messages_to_openai(messages: list[dict]) -> list[dict]:
    """Convert Anthropic message history to OpenAI format.

    Handles three cases:
      - Plain user/assistant text messages (same in both)
      - Assistant messages with content blocks (tool_use + text)
      - User messages with tool_result blocks
    """
    result: list[dict] = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")

        if isinstance(content, str):
            # Plain text message — same in both formats
            result.append({"role": role, "content": content})

        elif isinstance(content, list):
            if role == "assistant":
                # May contain text blocks and/or tool_use blocks
                text_parts = [b["text"] for b in content if b.get("type") == "text"]
                tool_uses = [b for b in content if b.get("type") == "tool_use"]

                tool_calls = [
                    {
                        "id": tu["id"],
                        "type": "function",
                        "function": {
                            "name": tu["name"],
                            "arguments": json.dumps(tu.get("input", {})),
                        },
                    }
                    for tu in tool_uses
                ]

                oai_msg: dict = {
                    "role": "assistant",
                    "content": " ".join(text_parts) if text_parts else None,
                }
                if tool_calls:
                    oai_msg["tool_calls"] = tool_calls
                result.append(oai_msg)

            elif role == "user":
                # May be a list of tool_result blocks
                tool_results = [b for b in content if b.get("type") == "tool_result"]
                non_tool = [b for b in content if b.get("type") != "tool_result"]

                # Each tool result becomes a separate "tool" role message
                for tr in tool_results:
                    result.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_use_id"],
                        "content": tr.get("content", ""),
                    })

                if non_tool:
                    # Fallback for unexpected mixed content
                    result.append({"role": "user", "content": str(non_tool)})

        else:
            result.append({"role": role, "content": str(content)})

    return result


# ── LLMClient ─────────────────────────────────────────────────────────────


class LLMClient:
    """Wraps Anthropic or OpenAI (LM Studio) behind a common streaming interface.

    Usage::

        client = LLMClient.from_settings(settings)
        response = await client.stream_turn(
            system=system_prompt,
            tools=TOOL_DEFINITIONS,   # Anthropic format
            messages=messages,        # Anthropic canonical list
            model=model,
            max_tokens=16384,
            on_text=lambda text: queue.put_nowait({...}),
        )
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.blocks:
                if isinstance(block, NormalizedToolUse):
                    result = call_tool(block.name, block.input)
                    tool_results.append((block.id, result))
            client.append_turn(messages, response, tool_results)
    """

    def __init__(
        self,
        *,
        use_local: bool = False,
        anthropic_key: str = "",
        local_key: str = "",
        local_base_url: str = "http://localhost:1234/v1",
        local_model: str = "local-model",
    ) -> None:
        self._use_local = use_local
        self._local_model = local_model

        if self._use_local:
            from openai import OpenAI  # lazy import — optional dependency

            # LM Studio doesn't require auth; the SDK still needs a non-empty string
            self._openai = OpenAI(api_key=local_key or "not-needed", base_url=local_base_url)
            self._anthropic = None
        else:
            import anthropic  # type: ignore[import]

            self._anthropic = anthropic.Anthropic(api_key=anthropic_key)
            self._openai = None

    @classmethod
    def from_settings(cls, settings: "Settings") -> "LLMClient":
        return cls(
            use_local=settings.use_local_llm,
            anthropic_key=settings.anthropic_api_key,
            local_key=settings.local_llm_api_key,
            local_base_url=settings.local_llm_base_url,
            local_model=settings.local_llm_model,
        )

    @classmethod
    def from_project(cls, project_config_json: str | None, settings: "Settings") -> "LLMClient":
        """Create client honoring a project's use_local_llm override (falls back to Settings)."""
        import json as _json
        try:
            stored = _json.loads(project_config_json or '{}')
            use_local = stored.get('use_local_llm', settings.use_local_llm)
        except Exception:
            use_local = settings.use_local_llm
        return cls(
            use_local=use_local,
            anthropic_key=settings.anthropic_api_key,
            local_key=settings.local_llm_api_key,
            local_base_url=settings.local_llm_base_url,
            local_model=settings.local_llm_model,
        )

    @property
    def provider(self) -> str:
        return "local" if self._use_local else "anthropic"

    # ── Streaming ──────────────────────────────────────────────────────────

    async def stream_turn(
        self,
        *,
        system: str,
        tools: list[dict],
        messages: list[dict],
        model: str,
        max_tokens: int = 16384,
        on_text: Callable[[str], Awaitable[None]] | None = None,
    ) -> NormalizedResponse:
        """Run one LLM turn, streaming text to on_text. Returns NormalizedResponse."""
        if self._use_local:
            return await self._stream_openai(
                system=system,
                tools=tools,
                messages=messages,
                max_tokens=max_tokens,
                on_text=on_text,
            )
        return await self._stream_anthropic(
            system=system,
            tools=tools,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            on_text=on_text,
        )

    async def _stream_anthropic(
        self,
        *,
        system: str,
        tools: list[dict],
        messages: list[dict],
        model: str,
        max_tokens: int,
        on_text: Callable[[str], Awaitable[None]] | None,
    ) -> NormalizedResponse:
        assert self._anthropic is not None
        loop = asyncio.get_running_loop()

        def _run() -> NormalizedResponse:
            blocks: list[NormalizedToolUse | NormalizedTextBlock] = []
            with self._anthropic.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
                messages=messages,
            ) as stream:
                for event in stream:
                    if hasattr(event, "type") and event.type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta and getattr(delta, "type", None) == "text_delta":
                            text = delta.text
                            if on_text:
                                loop.call_soon_threadsafe(loop.create_task, on_text(text))

                response = stream.get_final_message()

            for block in response.content:
                btype = getattr(block, "type", None)
                if btype == "text":
                    blocks.append(NormalizedTextBlock(text=getattr(block, "text", "")))
                elif btype == "tool_use":
                    blocks.append(NormalizedToolUse(
                        id=getattr(block, "id", ""),
                        name=getattr(block, "name", ""),
                        input=getattr(block, "input", {}),
                    ))

            return NormalizedResponse(
                stop_reason=response.stop_reason or "end_turn",
                blocks=blocks,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        return await asyncio.to_thread(_run)

    async def _stream_openai(
        self,
        *,
        system: str,
        tools: list[dict],
        messages: list[dict],
        max_tokens: int,
        on_text: Callable[[str], Awaitable[None]] | None,
    ) -> NormalizedResponse:
        assert self._openai is not None
        loop = asyncio.get_running_loop()

        openai_messages = [{"role": "system", "content": system}] + _anthropic_messages_to_openai(messages)
        openai_tools = [_anthropic_tool_to_openai(t) for t in tools]

        def _run() -> NormalizedResponse:
            text_buffer = ""
            # Index → {id, name, arguments}
            tc_buffer: dict[int, dict[str, str]] = {}
            input_tokens = 0
            output_tokens = 0

            stream = self._openai.chat.completions.create(
                model=self._local_model,
                messages=openai_messages,
                tools=openai_tools if openai_tools else None,
                stream=True,
                max_tokens=max_tokens,
                # Request usage in the final streaming chunk; not all servers support
                # this but those that don't simply omit the field (no error).
                stream_options={"include_usage": True},
            )

            finish_reason = "stop"
            for chunk in stream:
                # Usage arrives on a usage-only chunk (choices=[]) at the end
                if hasattr(chunk, "usage") and chunk.usage:
                    input_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                    output_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0

                choice = chunk.choices[0] if chunk.choices else None
                if choice is None:
                    continue
                delta = choice.delta

                if delta.content:
                    text_buffer += delta.content
                    if on_text:
                        loop.call_soon_threadsafe(loop.create_task, on_text(delta.content))

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tc_buffer:
                            tc_buffer[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tc_buffer[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tc_buffer[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            tc_buffer[idx]["arguments"] += tc.function.arguments

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            # Build normalized blocks
            blocks: list[NormalizedToolUse | NormalizedTextBlock] = []
            if text_buffer:
                blocks.append(NormalizedTextBlock(text=text_buffer))
            for idx in sorted(tc_buffer.keys()):
                tc = tc_buffer[idx]
                try:
                    parsed_input = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    parsed_input = {"raw": tc["arguments"]}
                blocks.append(NormalizedToolUse(
                    id=tc["id"] or f"call_{idx}",
                    name=tc["name"],
                    input=parsed_input,
                ))

            stop_reason = "tool_use" if tc_buffer else "end_turn"
            if finish_reason == "stop":
                stop_reason = "end_turn"

            return NormalizedResponse(
                stop_reason=stop_reason,
                blocks=blocks,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        return await asyncio.to_thread(_run)

    # ── Message history helpers ───────────────────────────────────────────

    def append_turn(
        self,
        messages: list[dict],
        response: NormalizedResponse,
        tool_results: list[tuple[str, str]],
    ) -> None:
        """Append assistant + tool result turns to messages (Anthropic canonical format).

        Both providers produce the same in-memory format here so the agent loops
        are provider-agnostic. This Anthropic format is converted to OpenAI format
        lazily inside stream_turn if needed.
        """
        # Build assistant message in Anthropic format
        content_blocks: list[dict] = []
        for block in response.blocks:
            if isinstance(block, NormalizedTextBlock):
                content_blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, NormalizedToolUse):
                content_blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        messages.append({"role": "assistant", "content": content_blocks})

        # Append tool results as a single user message (Anthropic format)
        if tool_results:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": tid, "content": result}
                    for tid, result in tool_results
                ],
            })
