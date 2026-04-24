"""Anthropic SDK streaming loop for the Reviewer agent."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from smrt_agent.agents.reviewer.budget import TOOL_DEFINITIONS, compute_cost_usd
from smrt_agent.agents.reviewer.tools import fetch_url, list_files, read_file, write_file


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "reviewer.md"
    return prompt_path.read_text(encoding="utf-8")


def _dispatch_tool(name: str, inputs: dict[str, Any], project_path: Path) -> str:
    try:
        if name == "list_files":
            files = list_files(project_path, inputs.get("subdir", ""))
            return json.dumps(files)
        elif name == "read_file":
            return read_file(project_path, inputs["path"])
        elif name == "fetch_url":
            return fetch_url(inputs["url"])
        elif name == "write_file":
            return write_file(project_path, inputs["path"], inputs["content"])
        else:
            return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Error: {exc}"


async def run_reviewer(
    *,
    project_path: Path,
    api_key: str,
    model: str,
    budget_usd: float,
    queue: asyncio.Queue,
    container_ip: str | None = None,
) -> None:
    """Run the Reviewer agent loop. Puts SSE event dicts into `queue`."""
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    task_description = f"Perform initialization audit for the project at {project_path}."
    if container_ip:
        task_description += f" The sandbox is running at container IP {container_ip}:8080."

    messages: list[dict] = [{"role": "user", "content": task_description}]
    total_input = 0
    total_output = 0

    while True:
        with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        ) as stream:
            for event in stream:
                if hasattr(event, "type") and event.type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", None) == "text_delta":
                        await queue.put({
                            "type": "text_delta",
                            "text": delta.text,
                            "agent": "reviewer",
                            "ts": _ts(),
                        })

            response = stream.get_final_message()

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens

        cost = compute_cost_usd(total_input, total_output, model)
        if cost >= budget_usd:
            await queue.put({
                "type": "budget_exceeded",
                "cost_usd": round(cost, 4),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "ts": _ts(),
            })
            return

        if response.stop_reason == "end_turn":
            await queue.put({
                "type": "done",
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_usd": round(cost, 4),
                "ts": _ts(),
            })
            return

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    await queue.put({
                        "type": "tool_use",
                        "agent": "reviewer",
                        "tool": block.name,
                        "input": block.input,
                        "ts": _ts(),
                    })
                    result = _dispatch_tool(block.name, block.input, project_path)
                    await queue.put({
                        "type": "tool_result",
                        "agent": "reviewer",
                        "tool": block.name,
                        "result": result[:2000],
                        "ts": _ts(),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        await queue.put({
            "type": "error",
            "message": f"Unexpected stop_reason: {response.stop_reason}",
            "ts": _ts(),
        })
        return
