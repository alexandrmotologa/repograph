"""Data models for code knowledge graph, symbols, relationships, and blast radius analysis."""

from enum import StrEnum

from pydantic import BaseModel, Field


class SymbolKind(StrEnum):
    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"


class EdgeType(StrEnum):
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    EXTENDS = "EXTENDS"
    IMPLEMENTS = "IMPLEMENTS"
    CONTAINS = "CONTAINS"


class ImpactCategory(StrEnum):
    CRITICAL = "CRITICAL"  # Public API routes, controllers, CLI entrypoints
    HIGH = "HIGH"  # Domain aggregate roots, service boundaries
    MEDIUM = "MEDIUM"  # Internal helpers, private utility methods
    TEST = "TEST"  # Unit or integration tests verifying the path


class ImportItem(BaseModel):
    """An imported module or symbol within a file."""

    source_module: str
    imported_name: str
    alias: str | None = None
    line_number: int = 1
    is_wildcard: bool = False


class CallSite(BaseModel):
    """A call expression invocation site within a scope."""

    caller_id: str
    callee_name: str  # E.g. 'cancel_order', 'service.process', 'super.save'
    line_number: int
    file_path: str


class InheritanceRelation(BaseModel):
    """An inheritance or interface implementation relationship."""

    child_id: str
    parent_name: str
    relation: EdgeType = EdgeType.EXTENDS


class SymbolNode(BaseModel):
    """A semantic symbol node extracted from source code."""

    id: str  # Unique across repository: e.g. "services/order.py::OrderService.cancel"
    name: str  # Short symbol name: "cancel"
    qualified_name: str  # Scoped name: "OrderService.cancel"
    kind: SymbolKind
    file_path: str  # Normalized repository-relative path
    line_start: int
    line_end: int
    docstring: str | None = None
    parameters: list[str] = Field(default_factory=list)
    is_exported: bool = False
    is_entrypoint: bool = False
    complexity: int = 1

    @property
    def location_str(self) -> str:
        return f"{self.file_path}:{self.line_start}-{self.line_end}"


class CodeEdge(BaseModel):
    """A directed dependency or call relationship between code symbols."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    line_number: int | None = None
    file_path: str | None = None


class ParsedFile(BaseModel):
    """All symbols, imports, calls, and inheritance extracted from a file."""

    file_path: str
    language: str
    content_hash: str
    symbols: list[SymbolNode] = Field(default_factory=list)
    imports: list[ImportItem] = Field(default_factory=list)
    calls: list[CallSite] = Field(default_factory=list)
    inheritance: list[InheritanceRelation] = Field(default_factory=list)


class BlastRadiusNode(BaseModel):
    """A node affected in an upstream or downstream blast radius traversal."""

    node_id: str
    name: str
    kind: SymbolKind
    file_path: str
    depth: int
    category: ImpactCategory
    path_from_target: list[str] = Field(default_factory=list)


class BlastRadiusReport(BaseModel):
    """Comprehensive blast radius evaluation for a target symbol."""

    target_id: str
    target_name: str
    target_file: str
    score: float  # 0.0 to 100.0 score of refactoring risk
    upstream_callers: list[BlastRadiusNode] = Field(default_factory=list)
    downstream_callees: list[BlastRadiusNode] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    affected_entrypoints: list[str] = Field(default_factory=list)
    affected_tests: list[str] = Field(default_factory=list)
    total_impacted_symbols: int = 0


class CyclePath(BaseModel):
    """A cycle detected in the dependency graph."""

    cycle_type: str  # 'module' or 'symbol'
    nodes: list[str]  # In cycle order, e.g. [A, B, C, A]
    files: list[str] = Field(default_factory=list)


class CycleReport(BaseModel):
    """Report on circular dependencies."""

    cycles: list[CyclePath] = Field(default_factory=list)
    total_cycles: int = 0


class DeadCodeReport(BaseModel):
    """Report on unreachable or unreferenced symbols."""

    dead_symbols: list[SymbolNode] = Field(default_factory=list)
    total_dead: int = 0


class ModuleCoupling(BaseModel):
    """Coupling and instability metrics for a module/package."""

    module_name: str
    afferent_coupling: int  # Ca: incoming dependencies
    efferent_coupling: int  # Ce: outgoing dependencies
    instability: float  # I = Ce / (Ca + Ce), 0 = maximally stable, 1 = unstable


class RepoMetrics(BaseModel):
    """Aggregate health and structural metrics for repository."""

    total_files: int = 0
    total_symbols: int = 0
    total_edges: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    cycles_count: int = 0
    dead_symbols_count: int = 0
    avg_complexity: float = 1.0
    modules_coupling: list[ModuleCoupling] = Field(default_factory=list)
    top_bottlenecks: list[tuple[str, int]] = Field(default_factory=list)
