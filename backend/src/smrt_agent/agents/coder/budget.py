"""Tool definitions and cost computation for the Coder agent."""
from smrt_agent.agents.reviewer.budget import compute_cost_usd  # reuse

_BASE_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_files",
        "description": "List source files in the project. Returns relative paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subdir": {"type": "string", "description": "Subdirectory to list."}
            },
            "required": [],
        },
    },
    {
        "name": "read_source_file",
        "description": "Read a source file. Cannot read from .smrt/, tests/, or docs/.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to source file."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_source_file",
        "description": "Write/overwrite a source file. Cannot write to .smrt/, tests/, or docs/.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path."},
                "content": {"type": "string", "description": "Full new file content."},
            },
            "required": ["path", "content"],
        },
    },
]

_ASK_QA_TOOL: dict = {
    "name": "ask_qa",
    "description": (
        "Ask the QA agent a clarifying question about the bug or expected behavior. "
        "Use this before writing your fix when you need to understand what correct behavior "
        "looks like. Limited to a fixed number of questions per attempt."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Your specific question about the bug or expected behavior.",
            }
        },
        "required": ["question"],
    },
}

# Backward-compatible alias used by existing import sites.
TOOL_DEFINITIONS = _BASE_TOOL_DEFINITIONS


def get_tool_definitions(with_ask_qa: bool = False) -> list[dict]:
    """Return tool list, optionally including the ask_qa consultation tool."""
    if with_ask_qa:
        return _BASE_TOOL_DEFINITIONS + [_ASK_QA_TOOL]
    return _BASE_TOOL_DEFINITIONS
