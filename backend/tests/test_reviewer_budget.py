import pytest
from smrt_agent.agents.reviewer.budget import compute_cost_usd, TOOL_DEFINITIONS


def test_opus_cost_input_only():
    cost = compute_cost_usd(1_000_000, 0, "claude-opus-4-7")
    assert abs(cost - 3.00) < 0.001


def test_opus_cost_output_only():
    cost = compute_cost_usd(0, 1_000_000, "claude-opus-4-7")
    assert abs(cost - 15.00) < 0.001


def test_sonnet_cost_mixed():
    cost = compute_cost_usd(1_000_000, 1_000_000, "claude-sonnet-4-6")
    assert abs(cost - 1.80) < 0.001  # 0.30 + 1.50


def test_unknown_model_falls_back_to_sonnet():
    cost = compute_cost_usd(1_000_000, 0, "claude-unknown-99")
    assert abs(cost - 0.30) < 0.001


def test_zero_tokens_zero_cost():
    assert compute_cost_usd(0, 0, "claude-opus-4-7") == 0.0


def test_tool_definitions_have_required_tools():
    names = {t["name"] for t in TOOL_DEFINITIONS}
    assert names == {"list_files", "read_file", "fetch_url", "write_file"}


def test_tool_definitions_have_input_schema():
    for tool in TOOL_DEFINITIONS:
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"
