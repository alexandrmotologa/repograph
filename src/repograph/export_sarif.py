"""SARIF 2.1.0 report exporter for GitHub Code Scanning and CI/CD static analysis."""

import json
from typing import Any

import networkx as nx

from repograph.analyzer.cycles import CycleDetector
from repograph.analyzer.dead_code import DeadCodeHunter
from repograph.analyzer.linter import ArchitecturalLinter
from repograph.config import ArchitecturalRules


class SarifExporter:
    """Exports RepoGraph analysis findings into OASIS standard SARIF 2.1.0 format."""

    def __init__(self, graph: nx.DiGraph, rules: ArchitecturalRules | None = None) -> None:
        self.graph = graph
        self.rules = rules or ArchitecturalRules()
        self.cycle_det = CycleDetector(graph)
        self.dead_hunter = DeadCodeHunter(graph)
        self.linter = ArchitecturalLinter(graph, self.rules)

    def generate_sarif(self) -> dict[str, Any]:
        """Generate SARIF JSON object."""
        rules_dict = [
            {
                "id": "RG001",
                "name": "CircularDependency",
                "shortDescription": {"text": "Circular dependency loop detected"},
                "fullDescription": {
                    "text": "Modules or files contain a cyclical import loop which harms maintainability and modularity."
                },
                "defaultConfiguration": {"level": "error"},
            },
            {
                "id": "RG002",
                "name": "UnreferencedDeadCode",
                "shortDescription": {"text": "Unreferenced unreachable symbol"},
                "fullDescription": {
                    "text": "Symbol has zero incoming calls, imports, or inheritance links across the codebase."
                },
                "defaultConfiguration": {"level": "warning"},
            },
            {
                "id": "RG003",
                "name": "ArchitecturalConstraintViolation",
                "shortDescription": {"text": "Architectural boundary rule violated"},
                "fullDescription": {
                    "text": "An import or dependency violates forbidden layer boundary rules defined in configuration."
                },
                "defaultConfiguration": {"level": "error"},
            },
        ]

        results = []

        # 1. Circular dependencies
        cycle_report = self.cycle_det.detect_module_cycles()
        for cycle in cycle_report.cycles:
            loop_str = " -> ".join(cycle.nodes)
            first_file = cycle.files[0] if cycle.files else "codebase"
            results.append(
                {
                    "ruleId": "RG001",
                    "level": "error",
                    "message": {"text": f"Circular import loop detected: {loop_str}"},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": first_file.replace("\\", "/")},
                                "region": {"startLine": 1},
                            }
                        }
                    ],
                }
            )

        # 2. Dead code
        dead_report = self.dead_hunter.find_dead_code(include_exported=False)
        for sym in dead_report.dead_symbols:
            results.append(
                {
                    "ruleId": "RG002",
                    "level": "warning",
                    "message": {
                        "text": f"Dead code candidate: '{sym.qualified_name}' ({sym.kind.value}) is unreferenced across the codebase."
                    },
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": sym.file_path.replace("\\", "/")},
                                "region": {
                                    "startLine": sym.line_start,
                                    "endLine": sym.line_end,
                                },
                            }
                        }
                    ],
                }
            )

        # 3. Architectural Linting
        lint_report = self.linter.lint()
        for v in lint_report.violations:
            loc_parts = v.source_location.split(":")
            f_path = loc_parts[0]
            l_num = int(loc_parts[1]) if len(loc_parts) > 1 and loc_parts[1].isdigit() else 1
            results.append(
                {
                    "ruleId": "RG003",
                    "level": "error" if v.severity == "error" else "warning",
                    "message": {"text": v.message},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": f_path.replace("\\", "/")},
                                "region": {"startLine": l_num},
                            }
                        }
                    ],
                }
            )

        return {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "RepoGraph",
                            "version": "0.1.0",
                            "informationUri": "https://github.com/alexandrmotologa/repograph",
                            "rules": rules_dict,
                        }
                    },
                    "results": results,
                }
            ],
        }

    def to_json(self) -> str:
        """Export SARIF structure to JSON string."""
        return json.dumps(self.generate_sarif(), indent=2)
