"""Streaming loop for the QA agent (provider-agnostic via LLMClient)."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smrt_agent.agents.qa.budget import TOOL_DEFINITIONS, compute_cost_usd
from smrt_agent.agents.budget_gateway import handle_budget_pause
from smrt_agent.agents.qa.tools import (
    write_test_file, run_pytest, write_bug_ticket,
    write_test_status, append_bugs_resolved,
)
from smrt_agent.agents.reviewer.tools import list_files, read_file
from smrt_agent.llm import LLMClient, NormalizedToolUse


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "qa.md"
    return prompt_path.read_text(encoding="utf-8")


async def _dispatch_tool(name: str, inputs: dict[str, Any], project_path: Path) -> tuple[str, str | None]:
    """Returns (result_str, ticket_id_if_written).

    run_pytest is offloaded to a thread because subprocess.run blocks the
    asyncio loop for the full pytest duration (potentially 60+ seconds with
    a hung test suite), which would freeze SSE events and make the UI appear
    stuck.
    """
    ticket_id = None
    try:
        if name == "list_files":
            result = json.dumps(list_files(project_path, inputs.get("subdir", "")))
        elif name == "read_file":
            result = read_file(project_path, inputs["path"])
        elif name == "write_test_file":
            result = write_test_file(project_path, inputs["filename"], inputs["content"])
        elif name == "run_pytest":
            result = await asyncio.to_thread(run_pytest, project_path)
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
    llm_client: LLMClient,
    model: str,
    budget_usd: float,
    queue: asyncio.Queue,
    prior_fix_context: str | None = None,
    job_id: str | None = None,
) -> str | None:
    """Run the QA agent. Returns ticket_id if bugs found, None if all tests pass."""
    system_prompt = _load_system_prompt()

    project_md = project_path / ".smrt" / "Project.md"
    context = (
        project_md.read_text(encoding="utf-8")
        if project_md.exists()
        else "(No Project.md found — survey the source tree directly.)"
    )

    task = f"Budget: ${budget_usd:.2f} USD — work efficiently.\n\nProject context:\n{context}\n"
    if prior_fix_context:
        task += f"\nPrevious fix attempt output:\n{prior_fix_context}\n"
    task += "\nGenerate and run black-box pytest tests. Write bug tickets for failures."

    messages: list[dict] = [{"role": "user", "content": task}]
    total_input = 0
    total_output = 0
    last_ticket_id: str | None = None

    while True:
        async def on_text(text: str) -> None:
            await queue.put({
                "type": "qa_text_delta",
                "text": text,
                "agent": "qa",
                "ts": _ts(),
            })

        response = await llm_client.stream_turn(
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=messages,
            model=model,
            on_text=on_text,
        )

        total_input += response.input_tokens
        total_output += response.output_tokens
        cost = compute_cost_usd(total_input, total_output, model)

        if cost >= budget_usd:
            should_continue, budget_usd = await handle_budget_pause(
                job_id=job_id,
                cost=cost,
                budget_usd=budget_usd,
                queue=queue,
                total_input=total_input,
                total_output=total_output,
                ts_fn=_ts,
            )
            if not should_continue:
                return last_ticket_id

        if response.stop_reason == "end_turn":
            await queue.put({
                "type": "qa_done",
                "model": model,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_usd": round(cost, 4),
                "ticket_id": last_ticket_id,
                "ts": _ts(),
            })
            return last_ticket_id

        if response.stop_reason == "tool_use":
            tool_results: list[tuple[str, str]] = []
            for block in response.blocks:
                if isinstance(block, NormalizedToolUse):
                    await queue.put({
                        "type": "tool_use",
                        "agent": "qa",
                        "tool": block.name,
                        "input": block.input,
                        "ts": _ts(),
                    })
                    result, ticket_id = await _dispatch_tool(block.name, block.input, project_path)
                    if ticket_id:
                        last_ticket_id = ticket_id
                    await queue.put({
                        "type": "tool_result",
                        "agent": "qa",
                        "tool": block.name,
                        "result": result[:2000],
                        "ts": _ts(),
                    })
                    tool_results.append((block.id, result))

            llm_client.append_turn(messages, response, tool_results)
            continue

        await queue.put({
            "type": "error",
            "message": f"QA agent unexpected stop_reason: {response.stop_reason}",
            "ts": _ts(),
        })
        return last_ticket_id
