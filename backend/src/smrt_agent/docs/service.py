from pathlib import Path

from smrt_agent.docs.backends import ObsidianBackend
from smrt_agent.docs.parser import load_and_parse


async def generate_docs(project_path: Path) -> dict[str, int]:
    """Parse .smrt/Project.md and write Obsidian-friendly docs to docs/.

    Returns {"backends": int, "endpoints": int}.
    """
    module, endpoints = load_and_parse(project_path)
    backend = ObsidianBackend(project_path)
    await backend.upsert_module_doc(module)
    for endpoint in endpoints:
        await backend.upsert_endpoint_doc(endpoint)
    return {"backends": 1, "endpoints": len(endpoints)}
