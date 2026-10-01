"""Architectural rule linter enforcing boundary rules and layer constraints."""

import fnmatch

import networkx as nx
from pydantic import BaseModel, Field

from repograph.analyzer.coupling import CouplingAnalyzer
from repograph.config import ArchitecturalRules
from repograph.models import EdgeType, SymbolKind


class LintViolation(BaseModel):
    """An architectural rule violation."""

    rule_type: str  # 'forbidden_import', 'instability', 'complexity', 'cycle'
    source_location: str  # file:line or symbol
    target_location: str | None = None
    message: str
    severity: str = "error"  # 'error' or 'warning'


class LintReport(BaseModel):
    """Result of running architectural linter."""

    total_violations: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    violations: list[LintViolation] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.errors_count == 0


class ArchitecturalLinter:
    """Verifies codebase architecture and boundaries against configured rules."""

    def __init__(self, graph: nx.DiGraph, rules: ArchitecturalRules) -> None:
        self.graph = graph
        self.rules = rules

    def lint(self) -> LintReport:
        """Run all architectural checks and return aggregated violations."""
        violations: list[LintViolation] = []

        # 1. Check forbidden imports
        for rule in self.rules.forbidden_imports:
            from_pat = rule.from_pattern.replace("\\", "/")
            to_pat = rule.to_pattern.replace("\\", "/")

            for u, v, data in self.graph.edges(data=True):
                edge_type = data.get("edge_type", "")
                if edge_type in (EdgeType.IMPORTS.value, EdgeType.CALLS.value):
                    u_file = self.graph.nodes[u].get("file_path", "")
                    v_file = self.graph.nodes[v].get("file_path", "")
                    u_line = data.get("line_number", 1) or 1

                    if not u_file or not v_file:
                        continue

                    # Match patterns using fnmatch
                    if self._matches_pattern(u_file, from_pat) and self._matches_pattern(
                        v_file, to_pat
                    ):
                        msg = (
                            rule.message
                            or f"Forbidden dependency: '{u_file}' is not allowed to import '{v_file}'"
                        )
                        violations.append(
                            LintViolation(
                                rule_type="forbidden_import",
                                source_location=f"{u_file}:{u_line}",
                                target_location=v_file,
                                message=msg,
                                severity=rule.severity,
                            )
                        )

        # 2. Check Martin Instability constraints
        if self.rules.instability_rules:
            analyzer = CouplingAnalyzer(self.graph)
            metrics = analyzer.compute_metrics()
            for rule in self.rules.instability_rules:
                mod_pat = rule.module_pattern.replace("\\", "/")
                for mc in metrics.modules_coupling:
                    if self._matches_pattern(mc.module_name, mod_pat):
                        if mc.instability > rule.max_instability:
                            violations.append(
                                LintViolation(
                                    rule_type="instability",
                                    source_location=mc.module_name,
                                    message=(
                                        f"Module '{mc.module_name}' instability I={mc.instability:.2f} "
                                        f"exceeds maximum allowed {rule.max_instability:.2f} "
                                        f"(Ca={mc.afferent_coupling}, Ce={mc.efferent_coupling})"
                                    ),
                                    severity="error",
                                )
                            )

        # 3. Check cyclomatic complexity threshold
        if self.rules.max_complexity > 0:
            for node_id, data in self.graph.nodes(data=True):
                if data.get("kind") in (
                    SymbolKind.FUNCTION.value,
                    SymbolKind.METHOD.value,
                ):
                    comp = data.get("complexity", 1)
                    if comp > self.rules.max_complexity:
                        f_path = data.get("file_path", "")
                        l_start = data.get("line_start", 1)
                        q_name = data.get("qualified_name", node_id)
                        violations.append(
                            LintViolation(
                                rule_type="complexity",
                                source_location=f"{f_path}:{l_start}",
                                message=f"Symbol '{q_name}' complexity {comp} exceeds limit of {self.rules.max_complexity}",
                                severity="warning",
                            )
                        )

        errors = sum(1 for v in violations if v.severity == "error")
        warnings = sum(1 for v in violations if v.severity == "warning")

        return LintReport(
            total_violations=len(violations),
            errors_count=errors,
            warnings_count=warnings,
            violations=violations,
        )

    @staticmethod
    def _matches_pattern(path_str: str, pattern: str) -> bool:
        norm = path_str.replace("\\", "/").lstrip("/")
        pat = pattern.replace("\\", "/").lstrip("/")

        if fnmatch.fnmatch(norm, pat):
            return True

        # Handle directory prefix: 'domain/*' matching 'domain/order/service.py'
        if pat.endswith("/*") or pat.endswith("/**"):
            base = pat.rstrip("/*")
            if norm == base or norm.startswith(f"{base}/"):
                return True

        return False
