"""Tool definitions and cost computation for the QA agent."""
from smrt_agent.agents.reviewer.budget import compute_cost_usd  # reuse

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_files",
        "description": "List all source files in the project tree. Returns relative paths. Skips .smrt/ and secrets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subdir": {"type": "string", "description": "Subdirectory to list. Omit for whole project."}
            },
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "Read a source file from the project. Path is relative to project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_test_file",
        "description": "Write a pytest test file to .smrt/tests/. Filename must end with .py and contain no path separators.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename like 'test_users.py'."},
                "content": {"type": "string", "description": "Full Python test file content."},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "run_pytest",
        "description": "Run pytest against all tests in .smrt/tests/. Returns raw pytest output.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "write_bug_ticket",
        "description": "Write a bug ticket to .smrt/tickets/. Returns the ticket ID (YYYY-MM-DD-NNN).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "test_output": {"type": "string"},
            },
            "required": ["title", "description", "test_output"],
        },
    },
    {
        "name": "write_test_status",
        "description": "Write the test run summary to .smrt/test-status.md.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Markdown summary of test results."},
            },
            "required": ["content"],
        },
    },
    {
        "name": "append_bugs_resolved",
        "description": "Append a resolution entry to .smrt/bugs-resolved.md.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "resolution": {"type": "string"},
            },
            "required": ["ticket_id", "resolution"],
        },
    },
]
