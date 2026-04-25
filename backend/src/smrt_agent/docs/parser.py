import re
from pathlib import Path

from smrt_agent.docs.backends import EndpointDoc, ModuleDoc

_ENDPOINT_ROW_RE = re.compile(
    r"^\|\s*([A-Z]+)\s*\|\s*(/[^|]*?)\s*\|\s*(Yes|No)\s*\|\s*([^|]+?)\s*\|",
    re.IGNORECASE | re.MULTILINE,
)


def parse_endpoints(project_md: str) -> list[EndpointDoc]:
    endpoints: list[EndpointDoc] = []
    for m in _ENDPOINT_ROW_RE.finditer(project_md):
        method, path, auth_str, purpose = m.groups()
        if method.strip().upper() in {"METHOD", "---"}:
            continue
        endpoints.append(
            EndpointDoc(
                method=method.strip().upper(),
                path=path.strip(),
                auth_required=auth_str.strip().lower() == "yes",
                purpose=purpose.strip(),
            )
        )
    return endpoints


def parse_module_doc(project_md: str, project_name: str) -> ModuleDoc:
    purpose_m = re.search(r"## Purpose\s+(.+?)(?=\n##|\Z)", project_md, re.DOTALL)
    description = purpose_m.group(1).strip() if purpose_m else ""
    return ModuleDoc(name=project_name, description=description, file_path=".smrt/Project.md")


def load_and_parse(project_path: Path) -> tuple[ModuleDoc, list[EndpointDoc]]:
    project_md_path = project_path / ".smrt" / "Project.md"
    if not project_md_path.exists():
        return ModuleDoc(name=project_path.name, description="", file_path=".smrt/Project.md"), []
    text = project_md_path.read_text(encoding="utf-8")
    name_m = re.search(r"^# Project:\s*(.+)$", text, re.MULTILINE)
    project_name = name_m.group(1).strip() if name_m else project_path.name
    return parse_module_doc(text, project_name), parse_endpoints(text)
