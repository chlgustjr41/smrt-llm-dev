"""Anthropic SDK streaming loop for the QA agent."""
import asyncio
import json
from pathlib import Path
from typing import Any

import anthropic

from smrt_agent.agents.qa.budget import TOOL_DEFINITIONS, compute_cost_usd
from smrt_agent.agents.qa.tools import (
    write_test_file, run_pytest, write_bug_ticket,
    write_test_status, append_bugs_resolved,
)
from smrt_agent.agents.reviewer.tools import list_files, read_file


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "qa.md"
    return prompt_path.read_text(encoding="utf-8")


def _dispatch_tool(name: str, inputs: dict[str, Any], project_path: Path) -> tuple[str, str | None]:
    """Returns (result_str, ticket_id_if_written)."""
    ticket_id = None
    try:
        if name == "list_files":
            result = json.dumps(list_files(project_path, inputs.get("subdir", "")))
        elif name == "read_file":
            result = read_file(project_path, inputs["path"])
        elif name == "write_test_file":
            result = write_test_file(project_path, inputs["filename"], inputs["content"])
        elif name == "run_pytest":
            result = run_pytest(project_path)
        elif name == "write_bug_ticket":
            ticket_id = write_bug_ticket(
                project_path, inputs["title"], inputs["description"], inputs["test_output"]
            )
            result = ticket_id
        elif name == "write_test_status":
            result = write_test_status(project_path, inputs["content"])
        elif name == "append_bugs_resolved":
            result = append_bugs_resolved(project_path, inputs["ticket_id"], inputs["resolution"])
        else:
            result = f"Unknown tool: {name}"
    except Exception as exc:
        result = f"Error: {exc}"
    return result, ticket_id


async def run_qa_agent(
    *,
    project_path: Path,
    api_key: str,
    model: str,
    budget_usd: float,
    queue: asyncio.Queue,
    prior_fix_context: str | None = None,
) -> str | None:
    """Run the QA agent. Returns ticket_id if bugs found, None if all tests pass."""
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    project_md = project_path / ".smrt" / "Project.md"
    context = (
        project_md.read_text(encoding="utf-8")
        if project_md.exists()
        else "(No Project.md found — survey the source tree directly.)"
    )

    task = f"Project context:\n{context}\n"
    if prior_fix_context:
        task += f"\nPrevious fix attempt output:\n{prior_fix_context}\n"
    task += "\nGenerate and run black-box pytest tests. Write bug tickets for failures."

    messages: list[dict] = [{"role": "user", "content": task}]
    total_input = 0
    total_output = 0
    last_ticket_id: str | None = None

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
                        await queue.put({"type": "qa_text_delta", "text": delta.text})
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
            return last_ticket_id

        if response.stop_reason == "end_turn":
            await queue.put({
                "type": "qa_done",
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_usd": round(cost, 4),
                "ticket_id": last_ticket_id,
            })
            return last_ticket_id

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    await queue.put({
                        "type": "tool_use",
                        "agent": "qa",
                        "tool": block.name,
                        "input": block.input,
                    })
                    result, ticket_id = _dispatch_tool(block.name, block.input, project_path)
                    if ticket_id:
                        last_ticket_id = ticket_id
                    await queue.put({
                        "type": "tool_result",
                        "agent": "qa",
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
            "message": f"QA agent unexpected stop_reason: {response.stop_reason}",
        })
        return last_ticket_id
