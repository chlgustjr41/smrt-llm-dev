"""Token cost computation and Anthropic tool definitions for the Reviewer agent."""

# Pricing per 1 million tokens (as of April 2026)
_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-7": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-6": {"input": 0.30, "output": 1.50},
    "claude-haiku-4-5-20251001": {"input": 0.08, "output": 0.40},
}
_DEFAULT_PRICING = _PRICING["claude-sonnet-4-6"]


def compute_cost_usd(input_tokens: int, output_tokens: int, model: str) -> float:
    """Return approximate USD cost for a given token usage and model."""
    p = _PRICING.get(model, _DEFAULT_PRICING)
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_files",
        "description": (
            "List all source files in the project tree. "
            "Returns relative paths. Respects .gitignore and skips secrets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subdir": {
                    "type": "string",
                    "description": (
                        "Subdirectory to list (relative to project root). "
                        "Omit or pass '' for the whole project."
                    ),
                }
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
                "path": {
                    "type": "string",
                    "description": "Relative path to the file (e.g. 'src/main.py').",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "fetch_url",
        "description": (
            "Fetch a URL and return its body as text. "
            "Use to retrieve /openapi.json from the running sandbox container."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to fetch."}
            },
            "required": ["url"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write a file inside the project's .smrt/ directory. "
            "Use to write .smrt/Project.md with your findings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relative to project root. MUST start with '.smrt/'.",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
]
