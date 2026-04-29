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


# Tool definitions used only when documentation generation is enabled for the
# run. The Reviewer's loop appends these to TOOL_DEFINITIONS at runtime so
# that runs without the docs flag don't even surface these tools to the model
# (smaller token footprint, less ambiguity about what to do).
DOC_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "write_readme",
        "description": (
            "Write or replace the project's top-level README.md. Use ONLY when "
            "the project has no README or the existing README is sparse "
            "(stub, placeholder, or under ~10 lines of substantive content). "
            "Always read_file('README.md') FIRST to check before calling this. "
            "Content should be a general project overview: what it does, who "
            "uses it, how to run it, and key tech stack. Audience: a "
            "newcomer landing on the repo's GitHub page."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "Full README.md content as GitHub-flavored markdown. "
                        "Should include: title, 1-paragraph overview, install/"
                        "run instructions, project structure summary, and a "
                        "pointer to docs/ for technical details."
                    ),
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "write_docs_file",
        "description": (
            "Write a technical documentation file inside the project's docs/ "
            "directory. Use for file-structure-based deep dives that "
            "complement the auto-generated module/endpoint stubs. Examples: "
            "docs/architecture.md (high-level design), docs/modules/auth.md "
            "(per-module deep dive), docs/data-model.md (DB schema). "
            "Path MUST start with 'docs/' and end with '.md'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Path relative to project root, e.g. "
                        "'docs/architecture.md' or 'docs/modules/main.md'. "
                        "MUST start with 'docs/' and end with '.md'."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Obsidian-friendly markdown body. Use [[wiki-links]] "
                        "for cross-references between docs files. Include "
                        "code references via inline backticks for file paths."
                    ),
                },
            },
            "required": ["path", "content"],
        },
    },
]
