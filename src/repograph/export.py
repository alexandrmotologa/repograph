"""Graph export functionality for JSON, Graphviz DOT, and Mermaid markdown diagrams."""

import json
from pathlib import Path

import networkx as nx

from repograph.models import BlastRadiusReport, EdgeType, SymbolKind


class GraphExporter:
    """Exports code knowledge graph to diverse formats for CI/CD and documentation."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def to_json(self) -> str:
        """Export graph to JSON structure."""
        nodes = []
        for n, d in self.graph.nodes(data=True):
            nodes.append({"id": n, **d})

        edges = []
        for u, v, d in self.graph.edges(data=True):
            edges.append({"source": u, "target": v, **d})

        return json.dumps({"nodes": nodes, "edges": edges}, indent=2)

    def to_dot(self) -> str:
        """Export graph to Graphviz DOT format."""
        lines = ["digraph RepoGraph {", "  rankdir=LR;", "  node [shape=box, fontname=Helvetica];"]

        for n, d in self.graph.nodes(data=True):
            kind = d.get("kind", "")
            label = d.get("name", n)
            color = "lightblue" if kind == SymbolKind.CLASS.value else "lightgray"
            if d.get("is_entrypoint", False):
                color = "salmon"
            lines.append(
                f'  "{n}" [label="{label}\\n({kind})", style=filled, fillcolor="{color}"];'
            )

        for u, v, d in self.graph.edges(data=True):
            e_type = d.get("edge_type", "")
            style = "solid"
            if e_type == EdgeType.IMPORTS.value:
                style = "dashed"
            elif e_type in (EdgeType.EXTENDS.value, EdgeType.IMPLEMENTS.value):
                style = "bold"
            lines.append(f'  "{u}" -> "{v}" [label="{e_type}", style="{style}"];')

        lines.append("}")
        return "\n".join(lines)

    def to_mermaid(self, max_nodes: int = 100) -> str:
        """Export graph to a Mermaid flowchart diagram."""
        lines = ["flowchart TD"]

        # Subgraph by file
        files_map: dict[str, list[tuple[str, dict]]] = {}
        for n, d in list(self.graph.nodes(data=True))[:max_nodes]:
            f = d.get("file_path", "unknown")
            files_map.setdefault(f, []).append((n, d))

        subgraph_idx = 0
        node_id_map: dict[str, str] = {}
        counter = 0

        for f_path, nodes in files_map.items():
            subgraph_idx += 1
            lines.append(f'  subgraph S{subgraph_idx} ["{Path(f_path).name}"]')
            for n, d in nodes:
                counter += 1
                m_id = f"N{counter}"
                node_id_map[n] = m_id
                name = d.get("name", n).replace('"', "'")
                kind = d.get("kind", "sym")
                lines.append(f'    {m_id}["{name} ({kind})"]')
            lines.append("  end")

        for u, v, d in self.graph.edges(data=True):
            if u in node_id_map and v in node_id_map:
                u_m = node_id_map[u]
                v_m = node_id_map[v]
                e_type = d.get("edge_type", "")
                lines.append(f"  {u_m} -->|{e_type}| {v_m}")

        return "\n".join(lines)

    def export_blast_radius_mermaid(self, report: BlastRadiusReport) -> str:
        """Generate focused Mermaid diagram specifically illustrating blast radius impact."""
        lines = ["flowchart TD"]
        lines.append("  %% Blast Radius Traversal")
        lines.append("  classDef target fill:#ff4444,stroke:#fff,stroke-width:3px,color:#fff;")
        lines.append("  classDef critical fill:#ff9900,stroke:#333,stroke-width:2px,color:#000;")
        lines.append("  classDef testNode fill:#33b5e5,stroke:#333,stroke-width:1px,color:#000;")
        lines.append("  classDef highNode fill:#ffbb33,stroke:#333,stroke-width:1px,color:#000;")
        lines.append("  classDef defaultNode fill:#e0e0e0,stroke:#333,stroke-width:1px,color:#000;")

        target_m = "TARGET"
        lines.append(
            f'  {target_m}["TARGET: {report.target_name}\\n({report.target_file})"]:::target'
        )

        # Upstream callers
        for i, up in enumerate(report.upstream_callers[:20]):
            uid = f"UP_{i}"
            css_class = (
                "critical"
                if up.category.value == "CRITICAL"
                else ("testNode" if up.category.value == "TEST" else "highNode")
            )
            lines.append(f'  {uid}["{up.name}\\n({Path(up.file_path).name})"]:::{css_class}')
            lines.append(f"  {uid} -->|CALLS| {target_m}")

        # Downstream callees
        for i, down in enumerate(report.downstream_callees[:20]):
            did = f"DOWN_{i}"
            lines.append(f'  {did}["{down.name}\\n({Path(down.file_path).name})"]:::defaultNode')
            lines.append(f"  {target_m} -->|CALLS| {did}")

        return "\n".join(lines)
