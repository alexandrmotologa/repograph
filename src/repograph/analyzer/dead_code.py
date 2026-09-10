"""Dead code hunter finding unreferenced functions, classes, and methods."""

import networkx as nx

from repograph.models import DeadCodeReport, EdgeType, SymbolKind, SymbolNode


class DeadCodeHunter:
    """Identifies unreachable or uncalled code symbols."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def find_dead_code(self, include_exported: bool = False) -> DeadCodeReport:
        """Find symbols with zero incoming calls or imports."""
        dead_nodes: list[SymbolNode] = []

        # Known entrypoint names and lifecycle methods
        ignored_names = {
            "main",
            "handler",
            "app",
            "cli",
            "setUp",
            "tearDown",
            "init",
        }

        for node_id, data in self.graph.nodes(data=True):
            kind_str = data.get("kind", "")
            if kind_str in (SymbolKind.MODULE.value, SymbolKind.VARIABLE.value):
                continue

            name = data.get("name", "")
            file_path = data.get("file_path", "")

            # Ignore tests
            if "test" in file_path.lower() or name.startswith("test_") or name.endswith("Test"):
                continue

            # Ignore dunder methods: __init__, __str__, etc.
            if name.startswith("__") and name.endswith("__"):
                continue

            # Ignore framework lifecycle / entrypoint
            if name in ignored_names or data.get("is_entrypoint", False):
                continue

            if not include_exported and data.get("is_exported", False):
                # In library code, exported functions may be called by external users
                # We can inspect if the file is an __init__.py or index.ts
                if file_path.endswith("__init__.py") or file_path.endswith("index.ts"):
                    continue

            # Count incoming CALLS or IMPORTS
            incoming_calls = 0
            for pred in self.graph.predecessors(node_id):
                edge_data = self.graph.get_edge_data(pred, node_id) or {}
                e_type = edge_data.get("edge_type", "")
                if e_type in (
                    EdgeType.CALLS.value,
                    EdgeType.IMPORTS.value,
                    EdgeType.EXTENDS.value,
                    EdgeType.IMPLEMENTS.value,
                ):
                    incoming_calls += 1

            if incoming_calls == 0:
                dead_nodes.append(
                    SymbolNode(
                        id=node_id,
                        name=name,
                        qualified_name=data.get("qualified_name", name),
                        kind=SymbolKind(kind_str),
                        file_path=file_path,
                        line_start=data.get("line_start", 1),
                        line_end=data.get("line_end", 1),
                        complexity=data.get("complexity", 1),
                        is_exported=data.get("is_exported", False),
                    )
                )

        dead_nodes.sort(key=lambda x: (x.file_path, x.line_start))
        return DeadCodeReport(dead_symbols=dead_nodes, total_dead=len(dead_nodes))
