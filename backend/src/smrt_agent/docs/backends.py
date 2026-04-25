from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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
