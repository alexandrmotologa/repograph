"""Coupling, instability metrics, and codebase structural health analysis."""

from pathlib import Path

import networkx as nx

from repograph.models import EdgeType, ModuleCoupling, RepoMetrics, SymbolKind


class CouplingAnalyzer:
    """Computes Afferent Coupling (Ca), Efferent Coupling (Ce), and Instability (I) metrics."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def compute_metrics(
        self,
        cycles_count: int = 0,
        dead_symbols_count: int = 0,
    ) -> RepoMetrics:
        """Calculate aggregate codebase metrics."""
        total_symbols = 0
        total_complexity = 0
        languages: dict[str, int] = {}
        files: set[str] = set()

        # Group nodes by module / package
        modules: dict[str, set[str]] = {}

        for node_id, data in self.graph.nodes(data=True):
            f_path = data.get("file_path", "")
            if f_path:
                files.add(f_path)
                ext = Path(f_path).suffix.lower()
                languages[ext] = languages.get(ext, 0) + 1

                # Module grouping by directory or file
                mod_name = Path(f_path).parent.as_posix()
                if mod_name == ".":
                    mod_name = Path(f_path).stem
                modules.setdefault(mod_name, set()).add(node_id)

            kind = data.get("kind", "")
            if kind != SymbolKind.MODULE.value:
                total_symbols += 1
                total_complexity += data.get("complexity", 1)

        total_edges = self.graph.number_of_edges()
        avg_comp = round(total_complexity / max(1, total_symbols), 2)

        # Compute Module Coupling (Ca, Ce, Instability)
        coupling_list: list[ModuleCoupling] = []
        for mod_name, mod_nodes in modules.items():
            ca = 0  # Incoming from other modules
            ce = 0  # Outgoing to other modules

            for n in mod_nodes:
                for pred in self.graph.predecessors(n):
                    if pred not in mod_nodes:
                        edge_data = self.graph.get_edge_data(pred, n) or {}
                        if edge_data.get("edge_type") in (
                            EdgeType.CALLS.value,
                            EdgeType.IMPORTS.value,
                        ):
                            ca += 1

                for succ in self.graph.successors(n):
                    if succ not in mod_nodes:
                        edge_data = self.graph.get_edge_data(n, succ) or {}
                        if edge_data.get("edge_type") in (
                            EdgeType.CALLS.value,
                            EdgeType.IMPORTS.value,
                        ):
                            ce += 1

            total_c = ca + ce
            instability = round(ce / total_c, 2) if total_c > 0 else 0.0
            coupling_list.append(
                ModuleCoupling(
                    module_name=mod_name,
                    afferent_coupling=ca,
                    efferent_coupling=ce,
                    instability=instability,
                )
            )

        coupling_list.sort(key=lambda m: (-m.afferent_coupling, m.instability))

        # Top bottlenecks: symbols with highest in-degree (most heavily depended on)
        in_degrees = []
        for n, data in self.graph.nodes(data=True):
            if data.get("kind") in (
                SymbolKind.FUNCTION.value,
                SymbolKind.METHOD.value,
                SymbolKind.CLASS.value,
            ):
                in_deg = sum(
                    1
                    for p in self.graph.predecessors(n)
                    if (self.graph.get_edge_data(p, n) or {}).get("edge_type")
                    in (EdgeType.CALLS.value, EdgeType.IMPORTS.value)
                )
                if in_deg > 0:
                    in_degrees.append((data.get("name", n), in_deg))

        in_degrees.sort(key=lambda x: -x[1])
        top_bottlenecks = in_degrees[:10]

        return RepoMetrics(
            total_files=len(files),
            total_symbols=total_symbols,
            total_edges=total_edges,
            languages=languages,
            cycles_count=cycles_count,
            dead_symbols_count=dead_symbols_count,
            avg_complexity=avg_comp,
            modules_coupling=coupling_list,
            top_bottlenecks=top_bottlenecks,
        )
