from pathlib import Path

from smrt_agent.docs.backends import GitHubBackend, ObsidianBackend
from smrt_agent.docs.parser import load_and_parse


async def generate_docs(project_path: Path) -> dict[str, int]:
    """Parse .smrt/Project.md and write to GitHub + Obsidian backends.

    Returns {"backends": int, "endpoints": int}.
    """
    module, endpoints = load_and_parse(project_path)
    backends = [GitHubBackend(project_path), ObsidianBackend(project_path)]
    for backend in backends:
        await backend.upsert_module_doc(module)
        for endpoint in endpoints:
            await backend.upsert_endpoint_doc(endpoint)
    return {"backends": len(backends), "endpoints": len(endpoints)}
