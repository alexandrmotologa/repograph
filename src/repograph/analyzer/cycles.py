"""Circular dependency detection at file, module, and symbol levels using Tarjan SCC and Johnson algorithms."""

import itertools

import networkx as nx

from repograph.models import CyclePath, CycleReport, EdgeType, SymbolKind


class CycleDetector:
    """Detects cyclical dependencies in imports and call hierarchies with safety bounds."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def detect_module_cycles(self, max_cycles: int = 100) -> CycleReport:
        """Construct a module/file-level dependency graph and find simple cycles safely."""
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
            # Find non-trivial SCCs first to isolate cyclic components
            sccs = [scc for scc in nx.strongly_connected_components(file_graph) if len(scc) > 1]
            for scc in sccs:
                subg = file_graph.subgraph(scc)
                for c in itertools.islice(nx.simple_cycles(subg), max_cycles - len(cycles)):
                    if len(c) > 1:
                        closed_loop = c + [c[0]]
                        cycles.append(
                            CyclePath(
                                cycle_type="module",
                                nodes=closed_loop,
                                files=c,
                            )
                        )
                    if len(cycles) >= max_cycles:
                        break
                if len(cycles) >= max_cycles:
                    break
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

    def detect_symbol_cycles(self, max_cycles: int = 100) -> CycleReport:
        """Find recursive or mutual circular call loops among functions and methods with safety bounds."""
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
            sccs = [scc for scc in nx.strongly_connected_components(call_graph) if len(scc) > 1]
            for scc in sccs:
                subg = call_graph.subgraph(scc)
                for c in itertools.islice(nx.simple_cycles(subg), max_cycles - len(cycles)):
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
                    if len(cycles) >= max_cycles:
                        break
                if len(cycles) >= max_cycles:
                    break
        except Exception:
            pass

        cycles.sort(key=lambda x: len(x.nodes))
        return CycleReport(cycles=cycles, total_cycles=len(cycles))
