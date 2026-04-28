from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
import json
from pathlib import Path


@dataclass
class EndpointDoc:
    method: str
    path: str
    auth_required: bool
    purpose: str
    tags: list[str] = field(default_factory=list)


@dataclass
class ModuleDoc:
    name: str
    description: str
    file_path: str
    tags: list[str] = field(default_factory=list)


@dataclass
class DecisionDoc:
    slug: str
    title: str
    context: str
    decision: str
    consequences: str
    tags: list[str] = field(default_factory=list)


class DocBackend(ABC):
    @abstractmethod
    async def upsert_module_doc(self, module: ModuleDoc) -> None: ...

    @abstractmethod
    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None: ...

    @abstractmethod
    async def upsert_decision(self, decision: DecisionDoc) -> None: ...


class GitHubBackend(DocBackend):
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    async def upsert_module_doc(self, module: ModuleDoc) -> None:
        path = self.project_path / "docs" / "modules" / f"{module.name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        tags_line = f"\n\n**Tags:** {', '.join(module.tags)}" if module.tags else ""
        path.write_text(
            f"# {module.name}\n\n{module.description}\n\n**File:** `{module.file_path}`{tags_line}\n",
            encoding="utf-8",
        )

    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None:
        slug = endpoint.path.strip("/").replace("/", "_") or "root"
        filename = f"{endpoint.method}_{slug}.md"
        path = self.project_path / "docs" / "api" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        auth = "Required" if endpoint.auth_required else "None"
        path.write_text(
            f"# {endpoint.method} {endpoint.path}\n\n"
            f"**Authentication:** {auth}\n\n"
            f"**Purpose:** {endpoint.purpose}\n",
            encoding="utf-8",
        )
        await self._update_api_index()

    async def _update_api_index(self) -> None:
        api_dir = self.project_path / "docs" / "api"
        if not api_dir.exists():
            return
        entries = sorted(f.name for f in api_dir.glob("*.md") if f.name != "index.md")
        lines = ["# API Reference\n"] + [f"- [{e}]({e})" for e in entries]
        (api_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    async def upsert_decision(self, decision: DecisionDoc) -> None:
        path = self.project_path / "docs" / "decisions" / f"{decision.slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# {decision.title}\n\n"
            f"## Context\n{decision.context}\n\n"
            f"## Decision\n{decision.decision}\n\n"
            f"## Consequences\n{decision.consequences}\n",
            encoding="utf-8",
        )


class ObsidianBackend(DocBackend):
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def _frontmatter(self, type_: str, tags: list[str]) -> str:
        tag_str = json.dumps(tags)
        return (
            "---\n"
            f"type: {type_}\n"
            f"tags: {tag_str}\n"
            f"updated: {date.today().isoformat()}\n"
            "---\n\n"
        )

    async def upsert_module_doc(self, module: ModuleDoc) -> None:
        slug = module.name.replace(".", "__").replace("/", "__")
        path = self.project_path / "docs" / "modules" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self._frontmatter("module", module.tags)
            + f"# {module.name}\n\n{module.description}\n\n**File:** `{module.file_path}`\n",
            encoding="utf-8",
        )

    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None:
        slug = endpoint.path.strip("/").replace("/", "_") or "root"
        filename = f"{endpoint.method}_{slug}.md"
        path = self.project_path / "docs" / "api" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        auth = "Required" if endpoint.auth_required else "None"
        path.write_text(
            self._frontmatter("endpoint", endpoint.tags)
            + f"# {endpoint.method} {endpoint.path}\n\n"
            f"**Authentication:** {auth}\n\n"
            f"**Purpose:** {endpoint.purpose}\n",
            encoding="utf-8",
        )

    async def upsert_decision(self, decision: DecisionDoc) -> None:
        path = self.project_path / "docs" / "decisions" / f"{decision.slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self._frontmatter("decision", decision.tags)
            + f"# {decision.title}\n\n"
            f"## Context\n{decision.context}\n\n"
            f"## Decision\n{decision.decision}\n\n"
            f"## Consequences\n{decision.consequences}\n",
            encoding="utf-8",
        )


class JiraBackend(DocBackend):
    async def upsert_module_doc(self, module: ModuleDoc) -> None:
        raise NotImplementedError("Jira backend is a v2 feature")

    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None:
        raise NotImplementedError("Jira backend is a v2 feature")

    async def upsert_decision(self, decision: DecisionDoc) -> None:
        raise NotImplementedError("Jira backend is a v2 feature")


class ConfluenceBackend(DocBackend):
    async def upsert_module_doc(self, module: ModuleDoc) -> None:
        raise NotImplementedError("Confluence backend is a v2 feature")

    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None:
        raise NotImplementedError("Confluence backend is a v2 feature")

    async def upsert_decision(self, decision: DecisionDoc) -> None:
        raise NotImplementedError("Confluence backend is a v2 feature")
