"""Tool definitions and cost computation for the Coder agent."""
from smrt_agent.agents.reviewer.budget import compute_cost_usd  # reuse

TOOL_DEFINITIONS: list[dict] = [
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
