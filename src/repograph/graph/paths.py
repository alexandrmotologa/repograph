"""Call path tracing between arbitrary code symbols using shortest path and simple paths algorithms."""

import networkx as nx
from pydantic import BaseModel, Field

from repograph.models import EdgeType, SymbolKind


class PathStep(BaseModel):
    """A single hop along a call or dependency path."""

    from_id: str
    from_name: str
    from_file: str
    to_id: str
    to_name: str
    to_file: str
    edge_type: str = EdgeType.CALLS.value
    line_number: int | None = None


class PathResult(BaseModel):
    """Full directional path between source and target symbols."""

    source_id: str
    source_name: str
    target_id: str
    target_name: str
    steps: list[PathStep] = Field(default_factory=list)
    total_hops: int = 0


class PathFinder:
    """Finds directed call and dependency paths connecting symbols."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def find_shortest_path(self, source_query: str, target_query: str) -> PathResult | None:
        """Find the shortest directed path from source to target symbol."""
        src_id = self._resolve_node_id(source_query)
        tgt_id = self._resolve_node_id(target_query)

        if not src_id or not tgt_id:
            return None

        # Build sub-graph containing only call and import transitions
        active_graph = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            e_type = data.get("edge_type", "")
            if e_type in (
                EdgeType.CALLS.value,
                EdgeType.IMPORTS.value,
                EdgeType.EXTENDS.value,
                EdgeType.IMPLEMENTS.value,
            ):
                active_graph.add_edge(u, v, **data)

        if not active_graph.has_node(src_id) or not active_graph.has_node(tgt_id):
            return None

        try:
            path_nodes = nx.shortest_path(active_graph, source=src_id, target=tgt_id)
            return self._build_path_result(src_id, tgt_id, path_nodes)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def find_all_paths(
        self,
        source_query: str,
        target_query: str,
        max_paths: int = 5,
        cutoff: int = 8,
    ) -> list[PathResult]:
        """Find up to max_paths simple paths between source and target."""
        src_id = self._resolve_node_id(source_query)
        tgt_id = self._resolve_node_id(target_query)

        if not src_id or not tgt_id:
            return []

        active_graph = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            e_type = data.get("edge_type", "")
            if e_type in (EdgeType.CALLS.value, EdgeType.IMPORTS.value):
                active_graph.add_edge(u, v, **data)

        if not active_graph.has_node(src_id) or not active_graph.has_node(tgt_id):
            return []

        results: list[PathResult] = []
        try:
            raw_paths = list(
                nx.all_simple_paths(active_graph, source=src_id, target=tgt_id, cutoff=cutoff)
            )
            for p in raw_paths[:max_paths]:
                results.append(self._build_path_result(src_id, tgt_id, p))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

        return results

    def _resolve_node_id(self, query: str) -> str | None:
        if self.graph.has_node(query):
            return query

        clean_q = query.strip()
        matches = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get("kind") == SymbolKind.MODULE.value:
                continue
            qual = data.get("qualified_name", "")
            name = data.get("name", "")
            if clean_q in (qual, name) or qual.endswith(f".{clean_q}"):
                matches.append(node_id)

        return matches[0] if matches else None

    def _build_path_result(self, src_id: str, tgt_id: str, path_nodes: list[str]) -> PathResult:
        steps: list[PathStep] = []
        for i in range(len(path_nodes) - 1):
            u = path_nodes[i]
            v = path_nodes[i + 1]
            u_data = self.graph.nodes[u]
            v_data = self.graph.nodes[v]
            edge_data = self.graph.get_edge_data(u, v) or {}

            steps.append(
                PathStep(
                    from_id=u,
                    from_name=u_data.get("name", u),
                    from_file=u_data.get("file_path", ""),
                    to_id=v,
                    to_name=v_data.get("name", v),
                    to_file=v_data.get("file_path", ""),
                    edge_type=edge_data.get("edge_type", EdgeType.CALLS.value),
                    line_number=edge_data.get("line_number"),
                )
            )

        src_name = self.graph.nodes[src_id].get("name", src_id)
        tgt_name = self.graph.nodes[tgt_id].get("name", tgt_id)

        return PathResult(
            source_id=src_id,
            source_name=src_name,
            target_id=tgt_id,
            target_name=tgt_name,
            steps=steps,
            total_hops=len(steps),
        )
