import asyncio
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from smrt_agent.agents.reviewer.loop import run_reviewer


def _make_end_turn_response(input_tokens=100, output_tokens=50):
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [MagicMock(type="text", text="Audit complete.")]
    response.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    return response


def _make_tool_use_response(tool_name, tool_input, tool_use_id="tu_001"):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input
    tool_block.id = tool_use_id

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_block]
    response.usage = MagicMock(input_tokens=200, output_tokens=80)
    return response


@pytest.fixture
def project_path(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
    (tmp_path / "requirements.txt").write_text("fastapi\n")
    return tmp_path


@pytest.mark.asyncio
async def test_run_reviewer_emits_done_event(project_path):
    queue: asyncio.Queue = asyncio.Queue()

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.__iter__ = MagicMock(return_value=iter([]))
    mock_stream.get_final_message = MagicMock(return_value=_make_end_turn_response())

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream)

    with patch("smrt_agent.agents.reviewer.loop.anthropic.Anthropic", return_value=mock_client):
        await run_reviewer(
            project_path=project_path,
            api_key="test-key",
            model="claude-sonnet-4-6",
            budget_usd=1.50,
            queue=queue,
        )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    assert "done" in types
    done = next(e for e in events if e["type"] == "done")
    assert done["total_input_tokens"] == 100
    assert done["total_output_tokens"] == 50


@pytest.mark.asyncio
async def test_run_reviewer_executes_list_files_tool(project_path):
    queue: asyncio.Queue = asyncio.Queue()

    call_count = 0

    def get_final_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_use_response("list_files", {"subdir": ""})
        return _make_end_turn_response(input_tokens=300, output_tokens=100)

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.__iter__ = MagicMock(return_value=iter([]))
    mock_stream.get_final_message = MagicMock(side_effect=get_final_side_effect)

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream)

    with patch("smrt_agent.agents.reviewer.loop.anthropic.Anthropic", return_value=mock_client):
        await run_reviewer(
            project_path=project_path,
            api_key="test-key",
            model="claude-sonnet-4-6",
            budget_usd=1.50,
            queue=queue,
        )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    assert "tool_use" in types
    assert "tool_result" in types
    assert "done" in types


@pytest.mark.asyncio
async def test_run_reviewer_stops_on_budget_exceeded(project_path):
    queue: asyncio.Queue = asyncio.Queue()

    # 1M input tokens at $3/Mtok for Opus = $3.00, way over $0.01 budget
    response = _make_end_turn_response(input_tokens=1_000_000, output_tokens=0)

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.__iter__ = MagicMock(return_value=iter([]))
    mock_stream.get_final_message = MagicMock(return_value=response)

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream)

    with patch("smrt_agent.agents.reviewer.loop.anthropic.Anthropic", return_value=mock_client):
        await run_reviewer(
            project_path=project_path,
            api_key="test-key",
            model="claude-opus-4-7",
            budget_usd=0.01,
            queue=queue,
        )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    assert "budget_exceeded" in types
