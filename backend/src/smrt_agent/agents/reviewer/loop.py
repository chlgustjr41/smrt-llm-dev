"""Streaming loop for the Reviewer agent (provider-agnostic via LLMClient)."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smrt_agent.agents.reviewer.budget import (
    DOC_TOOL_DEFINITIONS,
    TOOL_DEFINITIONS,
    compute_cost_usd,
)
from smrt_agent.agents.reviewer.tools import (
    fetch_url,
    list_files,
    read_file,
    write_docs_file,
    write_file,
    write_readme,
)
from smrt_agent.agents.budget_gateway import handle_budget_pause
from smrt_agent.llm import LLMClient, NormalizedToolUse


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
        elif name == "write_readme":
            return write_readme(project_path, inputs["content"])
        elif name == "write_docs_file":
            return write_docs_file(project_path, inputs["path"], inputs["content"])
        else:
            return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Error: {exc}"


async def run_reviewer(
    *,
    project_path: Path,
    llm_client: LLMClient,
    model: str,
    budget_usd: float,
    queue: asyncio.Queue,
    container_ip: str | None = None,
    job_id: str | None = None,
    generate_docs: bool = True,
) -> None:
    """Run the Reviewer agent loop. Puts SSE event dicts into `queue`.

    `generate_docs` controls whether the agent is expected to also write
    a README.md (when missing/sparse) and technical docs/* files. When False
    the agent only does the audit (writes .smrt/Project.md) — useful for a
    pure inspection without touching the user's project files.

    The flag flows two places: (1) the doc-writing tools are only added to
    the tool list when enabled, so the model can't accidentally write docs
    on a "no-docs" run; (2) the task message tells the model what's
    expected so it doesn't waste cycles searching for absent tools.
    """
    system_prompt = _load_system_prompt()

    # Pick the tool set based on whether docs generation is enabled. Hiding
    # the doc tools from the model entirely on no-docs runs avoids an entire
    # class of "the model called write_readme by mistake" failures.
    tools = list(TOOL_DEFINITIONS)
    if generate_docs:
        tools = tools + DOC_TOOL_DEFINITIONS

    docs_task_clause = (
        " Documentation generation is ENABLED for this run: in addition to "
        ".smrt/Project.md, you should also (1) read_file('README.md') to see "
        "if the project has a substantive README — if it's missing or sparse "
        "(stub/placeholder/under ~10 lines), call write_readme with a clear "
        "project overview; and (2) call write_docs_file for at least "
        "docs/architecture.md (high-level design) and one or more "
        "docs/modules/*.md per major source module."
        if generate_docs
        else " Documentation generation is DISABLED for this run: write only "
        ".smrt/Project.md and stop. Do NOT attempt to modify README.md or "
        "create files under docs/ — those tools are not available this run."
    )

    task_description = (
        f"Perform initialization audit for the project at {project_path}. "
        f"Budget: ${budget_usd:.2f} USD — work efficiently and prioritize the most critical findings."
        f"{docs_task_clause}"
    )
    if container_ip:
        task_description += f" The sandbox is running at container IP {container_ip}:8080."

    messages: list[dict] = [{"role": "user", "content": task_description}]
    total_input = 0
    total_output = 0

    while True:
        async def on_text(text: str) -> None:
            await queue.put({
                "type": "text_delta",
                "text": text,
                "agent": "reviewer",
                "ts": _ts(),
            })

        response = await llm_client.stream_turn(
            system=system_prompt,
            tools=tools,
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
                return

        if response.stop_reason == "end_turn":
            await queue.put({
                "type": "done",
                "model": model,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_usd": round(cost, 4),
                "ts": _ts(),
            })
            return

        if response.stop_reason == "tool_use":
            tool_results: list[tuple[str, str]] = []
            for block in response.blocks:
                if isinstance(block, NormalizedToolUse):
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
                    tool_results.append((block.id, result))

            llm_client.append_turn(messages, response, tool_results)
            continue

        await queue.put({
            "type": "error",
            "message": f"Unexpected stop_reason: {response.stop_reason}",
            "ts": _ts(),
        })
        return
