"""Graph query engine for symbol searching, subgraph extraction, and serialization."""

import networkx as nx

from repograph.models import SymbolKind


class GraphQuery:
    """Provides querying, searching, and traversal utilities over the DiGraph."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def find_symbols(
        self,
        query: str,
        kind: SymbolKind | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search symbols by partial name, qualified name, or file path."""
        q = query.lower().strip()
        results: list[dict] = []

        for node_id, data in self.graph.nodes(data=True):
            if data.get("kind") == SymbolKind.MODULE.value and not q.startswith("module:"):
                # Skip modules unless explicitly requested
                continue

            if kind and data.get("kind") != kind.value:
                continue

            name = data.get("name", "").lower()
            qual = data.get("qualified_name", "").lower()
            file_p = data.get("file_path", "").lower()

            score = 0
            if q == name:
                score = 100
            elif q in qual:
                score = 80
            elif q in name:
                score = 60
            elif q in file_p:
                score = 40

            if score > 0 or not q:
                res = dict(data)
                res["id"] = node_id
                res["match_score"] = score
                results.append(res)

        results.sort(key=lambda r: (-r["match_score"], r["name"]))
        return results[:limit]

    def get_node(self, node_id: str) -> dict | None:
        """Retrieve attributes for a specific node ID."""
        if not self.graph.has_node(node_id):
            return None
        data = dict(self.graph.nodes[node_id])
        data["id"] = node_id
        return data

    def get_subgraph(
        self,
        node_id: str,
        upstream_depth: int = 2,
        downstream_depth: int = 2,
    ) -> nx.DiGraph:
        """Extract an ego-subgraph containing upstream callers and downstream callees."""
        if not self.graph.has_node(node_id):
            return nx.DiGraph()

        included_nodes: set[str] = {node_id}

        # Upstream: reverse traversal (predecessors)
        frontier: set[str] = {node_id}
        for _ in range(upstream_depth):
            next_frontier: set[str] = set()
            for cur in frontier:
                for pred in self.graph.predecessors(cur):
                    if pred not in included_nodes:
                        included_nodes.add(pred)
                        next_frontier.add(pred)
            frontier = next_frontier
            if not frontier:
                break

        # Downstream: forward traversal (successors)
        frontier = {node_id}
        for _ in range(downstream_depth):
            next_frontier = set()
            for cur in frontier:
                for succ in self.graph.successors(cur):
                    if succ not in included_nodes:
                        included_nodes.add(succ)
                        next_frontier.add(succ)
            frontier = next_frontier
            if not frontier:
                break

        return self.graph.subgraph(included_nodes).copy()

    def to_cytoscape_elements(self, subgraph: nx.DiGraph | None = None) -> list[dict]:
        """Convert graph to Cytoscape.js JSON elements format for interactive web rendering."""
        g = subgraph if subgraph is not None else self.graph
        elements: list[dict] = []

        for node_id, data in g.nodes(data=True):
            elements.append(
                {
                    "data": {
                        "id": node_id,
                        "label": data.get("name", node_id),
                        "qualified_name": data.get("qualified_name", ""),
                        "kind": data.get("kind", "function"),
                        "file_path": data.get("file_path", ""),
                        "line_start": data.get("line_start", 1),
                        "line_end": data.get("line_end", 1),
                        "complexity": data.get("complexity", 1),
                        "is_entrypoint": data.get("is_entrypoint", False),
                        "is_exported": data.get("is_exported", False),
                    }
                }
            )

        for u, v, data in g.edges(data=True):
            elements.append(
                {
                    "data": {
                        "id": f"{u}->{v}",
                        "source": u,
                        "target": v,
                        "edge_type": data.get("edge_type", "CALLS"),
                        "line_number": data.get("line_number"),
                    }
                }
            )

        return elements
