"""Streaming loop for the Coder agent (provider-agnostic via LLMClient)."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smrt_agent.agents.coder.budget import get_tool_definitions, compute_cost_usd
from smrt_agent.agents.coder.tools import read_source_file, write_source_file
from smrt_agent.agents.reviewer.tools import list_files
from smrt_agent.agents.budget_gateway import handle_budget_pause
from smrt_agent.llm import LLMClient, NormalizedToolUse, NormalizedTextBlock


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


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


async def _ask_qa_one_shot(
    *,
    question: str,
    ticket_content: str,
    llm_client: LLMClient,
    model: str,
) -> tuple[str, int, int]:
    """Ask the QA agent a one-shot clarifying question about the bug ticket.

    Returns (answer, input_tokens, output_tokens).
    """
    system = (
        "You are the QA engineer who wrote the bug ticket below. "
        "Answer the coder's question concisely and accurately. "
        "Focus on what the correct behavior should be and any relevant test details.\n\n"
        f"Bug ticket:\n{ticket_content}"
    )
    messages: list[dict] = [{"role": "user", "content": question}]
    response = await llm_client.stream_turn(
        system=system,
        tools=[],
        messages=messages,
        model=model,
        on_text=None,
    )
    answer = "".join(
        b.text for b in response.blocks if isinstance(b, NormalizedTextBlock)
    ).strip() or "(No response from QA agent)"
    return answer, response.input_tokens, response.output_tokens


async def run_coder_agent(
    *,
    project_path: Path,
    llm_client: LLMClient,
    model: str,
    budget_usd: float,
    queue: asyncio.Queue,
    ticket_content: str,
    pytest_output: str,
    llm_client_qa: LLMClient | None = None,
    model_qa: str | None = None,
    max_questions: int = 0,
    job_id: str | None = None,
) -> None:
    """Run the Coder agent to fix bugs described in ticket_content.

    When llm_client_qa/model_qa/max_questions are provided, the Coder can call
    ask_qa up to max_questions times per run to consult the QA agent.
    """
    system_prompt = _load_system_prompt()

    has_qa = llm_client_qa is not None and model_qa is not None and max_questions > 0
    tool_defs = get_tool_definitions(with_ask_qa=has_qa)
    questions_remaining = max_questions

    task = (
        f"Budget: ${budget_usd:.2f} USD — work efficiently.\n\n"
        f"Bug ticket to fix:\n\n{ticket_content}\n\n"
        f"Failing pytest output:\n\n```\n{pytest_output}\n```\n\n"
        f"Fix the source code so these tests pass."
    )
    if has_qa:
        task += f"\n\nYou have {max_questions} question(s) available to ask the QA agent via ask_qa if you need clarification."

    messages: list[dict] = [{"role": "user", "content": task}]
    total_input = 0
    total_output = 0

    while True:
        async def on_text(text: str) -> None:
            await queue.put({
                "type": "coder_text_delta",
                "text": text,
                "agent": "coder",
                "ts": _ts(),
            })

        response = await llm_client.stream_turn(
            system=system_prompt,
            tools=tool_defs,
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
                "type": "coder_done",
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
                        "agent": "coder",
                        "tool": block.name,
                        "input": block.input,
                        "ts": _ts(),
                    })

                    if block.name == "ask_qa":
                        if has_qa and questions_remaining > 0:
                            question = str(block.input.get("question", ""))
                            answer, qa_in, qa_out = await _ask_qa_one_shot(
                                question=question,
                                ticket_content=ticket_content,
                                llm_client=llm_client_qa,  # type: ignore[arg-type]
                                model=model_qa,  # type: ignore[arg-type]
                            )
                            questions_remaining -= 1
                            # Track QA consultation cost separately
                            from smrt_agent.agents.qa.budget import compute_cost_usd as _qa_cost
                            qa_call_cost = _qa_cost(qa_in, qa_out, model_qa)  # type: ignore[arg-type]
                            await queue.put({
                                "type": "qa_feedback_done",
                                "model": model_qa,
                                "total_input_tokens": qa_in,
                                "total_output_tokens": qa_out,
                                "cost_usd": round(qa_call_cost, 6),
                                "ts": _ts(),
                            })
                            remaining_note = (
                                f" ({questions_remaining} question(s) remaining)"
                                if questions_remaining > 0
                                else " (no more questions available)"
                            )
                            result = answer + remaining_note
                        elif questions_remaining <= 0:
                            result = "No more QA questions available for this attempt."
                        else:
                            result = "QA consultation not configured for this run."
                    else:
                        result = _dispatch_tool(block.name, block.input, project_path)

                    await queue.put({
                        "type": "tool_result",
                        "agent": "coder",
                        "tool": block.name,
                        "result": result[:2000],
                        "ts": _ts(),
                    })
                    tool_results.append((block.id, result))

            llm_client.append_turn(messages, response, tool_results)
            continue

        await queue.put({
            "type": "error",
            "message": f"Coder unexpected stop_reason: {response.stop_reason}",
            "ts": _ts(),
        })
        return
