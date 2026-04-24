"""Anthropic SDK streaming loop for the Coder agent."""
import asyncio
import json
from pathlib import Path
from typing import Any

import anthropic

from smrt_agent.agents.coder.budget import TOOL_DEFINITIONS, compute_cost_usd
from smrt_agent.agents.coder.tools import read_source_file, write_source_file
from smrt_agent.agents.reviewer.tools import list_files


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "coder.md"
    return prompt_path.read_text(encoding="utf-8")


def _dispatch_tool(name: str, inputs: dict[str, Any], project_path: Path) -> str:
    try:
        if name == "list_files":
            return json.dumps(list_files(project_path, inputs.get("subdir", "")))
        elif name == "read_source_file":
            return read_source_file(project_path, inputs["path"])
        elif name == "write_source_file":
            return write_source_file(project_path, inputs["path"], inputs["content"])
        else:
            return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Error: {exc}"


async def run_coder_agent(
    *,
    project_path: Path,
    api_key: str,
    model: str,
    budget_usd: float,
    queue: asyncio.Queue,
    ticket_content: str,
    pytest_output: str,
) -> None:
    """Run the Coder agent to fix bugs described in ticket_content."""
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    task = (
        f"Bug ticket to fix:\n\n{ticket_content}\n\n"
        f"Failing pytest output:\n\n```\n{pytest_output}\n```\n\n"
        f"Fix the source code so these tests pass."
    )
    messages: list[dict] = [{"role": "user", "content": task}]
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
                        await queue.put({"type": "coder_text_delta", "text": delta.text})
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
            })
            return

        if response.stop_reason == "end_turn":
            await queue.put({
                "type": "coder_done",
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_usd": round(cost, 4),
            })
            return

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    await queue.put({
                        "type": "tool_use",
                        "agent": "coder",
                        "tool": block.name,
                        "input": block.input,
                    })
                    result = _dispatch_tool(block.name, block.input, project_path)
                    await queue.put({
                        "type": "tool_result",
                        "agent": "coder",
                        "tool": block.name,
                        "result": result[:500],
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
            "message": f"Coder unexpected stop_reason: {response.stop_reason}",
        })
        return
