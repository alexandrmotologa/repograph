"""Generates a standalone, offline, single-file HTML report with embedded Cytoscape graph."""

import json
from pathlib import Path

import networkx as nx

from repograph.analyzer.blast_radius import BlastRadiusCalculator
from repograph.analyzer.coupling import CouplingAnalyzer
from repograph.analyzer.cycles import CycleDetector
from repograph.analyzer.dead_code import DeadCodeHunter
from repograph.graph.query import GraphQuery


class HtmlReportGenerator:
    """Creates a self-contained offline HTML visualizer containing embedded graph data."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph
        self.query = GraphQuery(graph)
        self.calc = BlastRadiusCalculator(graph)
        self.cycle_det = CycleDetector(graph)
        self.dead_hunter = DeadCodeHunter(graph)
        self.coupling_analyzer = CouplingAnalyzer(graph)

    def generate_html(self, title: str = "RepoGraph Codebase Intelligence Report") -> str:
        """Bundle graph data, HTML structure, styles, and Cytoscape.js logic into a single HTML file."""
        elements = self.query.to_cytoscape_elements()
        cycles = self.cycle_det.detect_module_cycles().model_dump()
        dead_code = self.dead_hunter.find_dead_code().model_dump()
        metrics = self.coupling_analyzer.compute_metrics().model_dump()

        # Precompute blast radius for top symbols
        blast_map = {}
        for node_id, data in list(self.graph.nodes(data=True))[:100]:
            if data.get("kind") != "module":
                report = self.calc.calculate(node_id)
                blast_map[node_id] = report.model_dump()

        graph_data_json = json.dumps(
            {
                "elements": elements,
                "cycles": cycles,
                "dead_code": dead_code,
                "metrics": metrics,
                "blast_cache": blast_map,
                "total_nodes": self.graph.number_of_nodes(),
                "total_edges": self.graph.number_of_edges(),
            }
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-primary: #090d13;
      --bg-secondary: #0f141c;
      --bg-card: rgba(15, 20, 28, 0.9);
      --border-color: rgba(255, 255, 255, 0.08);
      --text-primary: #f0f6fc;
      --text-secondary: #8b949e;
      --accent-cyan: #38bdf8;
      --accent-green: #34d399;
      --accent-yellow: #fbbf24;
      --accent-red: #f87171;
      --accent-purple: #c084fc;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg-primary);
      color: var(--text-primary);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }}
    header {{
      background-color: var(--bg-secondary);
      border-bottom: 1px solid var(--border-color);
      padding: 10px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      z-index: 20;
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; }}
    .logo-text {{
      font-weight: 800;
      font-size: 1.25rem;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #38bdf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .stat-badge {{
      font-family: 'JetBrains Mono', monospace;
      background-color: rgba(56, 189, 248, 0.1);
      color: var(--accent-cyan);
      border: 1px solid rgba(56, 189, 248, 0.25);
      padding: 3px 9px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .stat-badge.cycles {{
      background-color: rgba(248, 113, 113, 0.12);
      color: var(--accent-red);
      border-color: rgba(248, 113, 113, 0.3);
    }}
    .header-controls {{ display: flex; align-items: center; gap: 10px; }}
    .search-input {{
      background-color: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      color: var(--text-primary);
      padding: 6px 12px;
      font-size: 0.85rem;
      width: 220px;
      outline: none;
      font-family: inherit;
    }}
    .search-input:focus {{ border-color: var(--accent-cyan); }}
    .layout-container {{ display: flex; flex: 1; position: relative; overflow: hidden; }}
    #cy {{
      flex: 1;
      height: 100%;
      background-color: #06090e;
      background-image: radial-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px);
      background-size: 24px 24px;
    }}
    .inspector-drawer {{
      width: 400px;
      background-color: var(--bg-card);
      backdrop-filter: blur(16px);
      border-left: 1px solid var(--border-color);
      padding: 22px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      overflow-y: auto;
      z-index: 10;
      box-shadow: -8px 0 24px rgba(0, 0, 0, 0.4);
    }}
    .kind-badge {{
      display: inline-block;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      background: rgba(192, 132, 252, 0.15);
      color: var(--accent-purple);
      padding: 2px 8px;
      border-radius: 4px;
      margin-bottom: 6px;
    }}
    .score-card {{
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .score-val {{ font-family: 'JetBrains Mono', monospace; font-size: 2rem; font-weight: 800; }}
    .score-green {{ color: var(--accent-green); }}
    .score-yellow {{ color: var(--accent-yellow); }}
    .score-red {{ color: var(--accent-red); }}
    .tree-title {{ font-size: 0.8rem; font-weight: 600; text-transform: uppercase; color: var(--text-secondary); }}
    .tree-item {{
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 0.82rem;
      margin-top: 6px;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }}
    .tree-item:hover {{ background: rgba(56, 189, 248, 0.08); border-color: var(--accent-cyan); }}
    .tree-item .path {{ font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #64748b; }}
    button {{
      background-color: rgba(255, 255, 255, 0.04);
      color: var(--text-primary);
      border: 1px solid var(--border-color);
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.82rem;
    }}
    button:hover {{ background-color: rgba(255, 255, 255, 0.08); }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
</head>
<body>
  <header>
    <div class="brand">
      <div class="logo-text">RepoGraph</div>
      <span class="stat-badge" id="stat-nodes">0 symbols</span>
      <span class="stat-badge" id="stat-edges">0 edges</span>
      <span class="stat-badge" id="stat-cycles">0 cycles</span>
    </div>
    <div class="header-controls">
      <input type="text" id="search" class="search-input" placeholder="Search symbols (/)...">
      <button id="btn-fit">Fit Graph</button>
      <button id="btn-reset">Reset</button>
    </div>
  </header>

  <div class="layout-container">
    <div id="cy"></div>
    <aside class="inspector-drawer">
      <div>
        <div class="kind-badge" id="drawer-kind">SYMBOL</div>
        <h2 id="drawer-title" style="font-size: 1.15rem; font-weight: 700; word-break: break-word;">Select a Symbol</h2>
        <div id="drawer-file" style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: var(--text-secondary); margin-top: 4px;">Click any node in graph</div>
      </div>
      <div class="score-card">
        <div>
          <div style="font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase;">Blast Radius</div>
          <div class="score-val score-green" id="score-value">--/100</div>
        </div>
        <div style="text-align: right; font-size: 0.82rem; color: var(--text-secondary);">
          <div><strong id="count-callers" style="color:#fff; font-family:'JetBrains Mono'">0</strong> callers</div>
          <div><strong id="count-files" style="color:#fff; font-family:'JetBrains Mono'">0</strong> files</div>
        </div>
      </div>
      <div>
        <div class="tree-title">▲ Upstream Callers</div>
        <ul id="upstream-list" style="list-style: none;"></ul>
      </div>
      <div>
        <div class="tree-title">▼ Downstream Dependencies</div>
        <ul id="downstream-list" style="list-style: none;"></ul>
      </div>
    </aside>
  </div>

  <script>
    const DATA = {graph_data_json};
    let cy = null;

    window.addEventListener("DOMContentLoaded", () => {{
      document.getElementById("stat-nodes").textContent = `${{DATA.total_nodes}} symbols`;
      document.getElementById("stat-edges").textContent = `${{DATA.total_edges}} edges`;
      const cBadge = document.getElementById("stat-cycles");
      cBadge.textContent = `${{DATA.cycles.total_cycles}} cycles`;
      if (DATA.cycles.total_cycles > 0) cBadge.classList.add("cycles");

      cy = cytoscape({{
        container: document.getElementById("cy"),
        elements: DATA.elements,
        style: [
          {{ selector: "node", style: {{ "label": "data(label)", "color": "#f0f6fc", "font-family": "Inter, sans-serif", "font-size": "11px", "font-weight": 500, "text-valign": "bottom", "text-margin-y": "6px", "background-color": "#38bdf8", "width": 26, "height": 26, "border-width": 1.5, "border-color": "rgba(255,255,255,0.15)" }} }},
          {{ selector: 'node[kind = "class"]', style: {{ "background-color": "#c084fc", "shape": "round-rectangle", "width": 32, "height": 32 }} }},
          {{ selector: 'node[kind = "interface"]', style: {{ "background-color": "#fbbf24", "shape": "diamond", "width": 30, "height": 30 }} }},
          {{ selector: 'node[kind = "module"]', style: {{ "background-color": "#475569", "shape": "ellipse", "width": 20, "height": 20 }} }},
          {{ selector: "node[?is_entrypoint]", style: {{ "border-width": 3, "border-color": "#f87171" }} }},
          {{ selector: "edge", style: {{ "width": 1.5, "line-color": "#334155", "target-arrow-color": "#334155", "target-arrow-shape": "triangle", "curve-style": "bezier", "opacity": 0.65 }} }},
          {{ selector: ".highlighted-target", style: {{ "background-color": "#f87171", "border-color": "#ffffff", "border-width": 3.5, "width": 40, "height": 40, "z-index": 999 }} }},
          {{ selector: ".highlighted-upstream", style: {{ "background-color": "#fbbf24", "line-color": "#fbbf24", "target-arrow-color": "#fbbf24", "opacity": 1.0, "width": 32, "height": 32 }} }},
          {{ selector: ".highlighted-downstream", style: {{ "background-color": "#38bdf8", "line-color": "#38bdf8", "target-arrow-color": "#38bdf8", "opacity": 1.0, "width": 32, "height": 32 }} }},
          {{ selector: ".dimmed", style: {{ "opacity": 0.12 }} }}
        ],
        layout: {{ name: "cose", animate: false, randomize: false, componentSpacing: 90, nodeOverlap: 20, idealEdgeLength: 60 }}
      }});

      cy.on("tap", "node", (evt) => {{
        const node = evt.target;
        const nId = node.data("id");
        document.getElementById("drawer-kind").textContent = node.data("kind") || "SYMBOL";
        document.getElementById("drawer-title").textContent = node.data("label");
        document.getElementById("drawer-file").textContent = node.data("file_path");

        const rep = DATA.blast_cache[nId];
        if (rep) {{
          const sVal = document.getElementById("score-value");
          sVal.textContent = `${{rep.score}}/100`;
          sVal.className = "score-val " + (rep.score < 30 ? "score-green" : rep.score < 70 ? "score-yellow" : "score-red");
          document.getElementById("count-callers").textContent = rep.upstream_callers.length;
          document.getElementById("count-files").textContent = rep.affected_files.length;

          const uList = document.getElementById("upstream-list");
          uList.innerHTML = "";
          rep.upstream_callers.forEach(u => {{
            const li = document.createElement("li");
            li.className = "tree-item";
            li.innerHTML = `<strong>${{u.name}}</strong><span class="path">${{u.file_path}}</span>`;
            uList.appendChild(li);
          }});

          const dList = document.getElementById("downstream-list");
          dList.innerHTML = "";
          rep.downstream_callees.forEach(d => {{
            const li = document.createElement("li");
            li.className = "tree-item";
            li.innerHTML = `<strong>${{d.name}}</strong><span class="path">${{d.file_path}}</span>`;
            dList.appendChild(li);
          }});

          cy.elements().removeClass("highlighted-target highlighted-upstream highlighted-downstream dimmed").addClass("dimmed");
          node.removeClass("dimmed").addClass("highlighted-target");
          rep.upstream_callers.forEach(u => cy.getElementById(u.node_id).removeClass("dimmed").addClass("highlighted-upstream"));
          rep.downstream_callees.forEach(d => cy.getElementById(d.node_id).removeClass("dimmed").addClass("highlighted-downstream"));
        }}
      }});

      document.getElementById("btn-fit").addEventListener("click", () => cy.fit(undefined, 30));
      document.getElementById("btn-reset").addEventListener("click", () => cy.elements().removeClass("highlighted-target highlighted-upstream highlighted-downstream dimmed"));
      document.getElementById("search").addEventListener("input", (e) => {{
        const q = e.target.value.toLowerCase().trim();
        if (!q) {{ cy.elements().removeClass("dimmed"); return; }}
        cy.elements().addClass("dimmed");
        const matched = cy.nodes().filter(n => (n.data("label")||"").toLowerCase().includes(q) || (n.data("file_path")||"").toLowerCase().includes(q));
        matched.removeClass("dimmed");
        matched.connectedEdges().removeClass("dimmed");
      }});
    }});
  </script>
</body>
</html>
"""

    def export_to_file(
        self, output_path: Path, title: str = "RepoGraph Codebase Intelligence Report"
    ) -> Path:
        """Write self-contained HTML report to disk."""
        html_content = self.generate_html(title=title)
        output_path.write_text(html_content, encoding="utf-8")
        return output_path
