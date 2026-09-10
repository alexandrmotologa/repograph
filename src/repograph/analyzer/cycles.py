"""Circular dependency detection at file, module, and symbol levels using Tarjan SCC."""

import networkx as nx

from repograph.models import CyclePath, CycleReport, EdgeType, SymbolKind


class CycleDetector:
    """Detects cyclical dependencies in imports and call hierarchies."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def detect_module_cycles(self) -> CycleReport:
        """Construct a module/file-level dependency graph and find all simple cycles."""
        # 1. Build collapsed file/module graph
        file_graph = nx.DiGraph()

        for u, v, data in self.graph.edges(data=True):
            edge_type = data.get("edge_type", "")
            if edge_type in (EdgeType.IMPORTS.value, EdgeType.CALLS.value):
                u_file = self.graph.nodes[u].get("file_path", "")
                v_file = self.graph.nodes[v].get("file_path", "")
                if u_file and v_file and u_file != v_file:
                    file_graph.add_edge(u_file, v_file)

        cycles: list[CyclePath] = []
        try:
            # simple_cycles finds all elementary circuits
            found_cycles = list(nx.simple_cycles(file_graph))
            for c in found_cycles:
                if len(c) > 1:
                    # Close the loop visually: [A, B, A]
                    closed_loop = c + [c[0]]
                    cycles.append(
                        CyclePath(
                            cycle_type="module",
                            nodes=closed_loop,
                            files=c,
                        )
                    )
        except Exception:
            # Fallback to strongly connected components
            sccs = list(nx.strongly_connected_components(file_graph))
            for scc in sccs:
                if len(scc) > 1:
                    nodes_list = list(scc)
                    cycles.append(
                        CyclePath(
                            cycle_type="module",
                            nodes=nodes_list + [nodes_list[0]],
                            files=nodes_list,
                        )
                    )

        # Sort by cycle length
        cycles.sort(key=lambda x: len(x.nodes))
        return CycleReport(cycles=cycles, total_cycles=len(cycles))

    def detect_symbol_cycles(self) -> CycleReport:
        """Find recursive or mutual circular call loops among functions and methods."""
        call_graph = nx.DiGraph()

        for u, v, data in self.graph.edges(data=True):
            edge_type = data.get("edge_type", "")
            if edge_type == EdgeType.CALLS.value:
                u_kind = self.graph.nodes[u].get("kind", "")
                v_kind = self.graph.nodes[v].get("kind", "")
                if u_kind != SymbolKind.MODULE.value and v_kind != SymbolKind.MODULE.value:
                    if u != v:  # exclude direct recursion
                        call_graph.add_edge(u, v)

        cycles: list[CyclePath] = []
        try:
            for c in nx.simple_cycles(call_graph):
                if len(c) > 1:
                    closed = c + [c[0]]
                    files = list(
                        {
                            self.graph.nodes[n].get("file_path", "")
                            for n in c
                            if self.graph.has_node(n)
                        }
                    )
                    cycles.append(
                        CyclePath(
                            cycle_type="symbol",
                            nodes=closed,
                            files=files,
                        )
                    )
        except Exception:
            pass

        cycles.sort(key=lambda x: len(x.nodes))
        return CycleReport(cycles=cycles, total_cycles=len(cycles))
