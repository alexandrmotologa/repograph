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
  <style>
    :root {{
      --bg-primary: #0d1117;
      --bg-secondary: #161b22;
      --bg-card: rgba(22, 27, 34, 0.9);
      --border-color: #30363d;
      --text-primary: #f0f6fc;
      --text-secondary: #8b949e;
      --accent-cyan: #58a6ff;
      --accent-green: #3fb950;
      --accent-yellow: #d29922;
      --accent-red: #f85149;
      --accent-purple: #bc8cff;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg-primary);
      color: var(--text-primary);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }}
    header {{
      background-color: var(--bg-secondary);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .logo-text {{
      font-weight: 700;
      font-size: 1.25rem;
      background: linear-gradient(135deg, #58a6ff, #bc8cff);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .stat-badge {{
      background-color: rgba(88, 166, 255, 0.15);
      color: var(--accent-cyan);
      border: 1px solid rgba(88, 166, 255, 0.3);
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 0.8rem;
      font-weight: 600;
      margin-left: 8px;
    }}
    .stat-badge.cycles {{
      background-color: rgba(248, 81, 73, 0.15);
      color: var(--accent-red);
      border-color: rgba(248, 81, 73, 0.3);
    }}
    .search-input {{
      background-color: var(--bg-primary);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      color: var(--text-primary);
      padding: 6px 14px;
      font-size: 0.9rem;
      width: 260px;
      outline: none;
    }}
    .layout-container {{ display: flex; flex: 1; position: relative; overflow: hidden; }}
    #cy {{ flex: 1; height: 100%; background-color: #0b0e14; }}
    .inspector-drawer {{
      width: 380px;
      background-color: var(--bg-card);
      backdrop-filter: blur(12px);
      border-left: 1px solid var(--border-color);
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      overflow-y: auto;
    }}
    .score-card {{
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .score-val {{ font-size: 1.8rem; font-weight: 700; }}
    .score-green {{ color: var(--accent-green); }}
    .score-yellow {{ color: var(--accent-yellow); }}
    .score-red {{ color: var(--accent-red); }}
    .tree-title {{ font-size: 0.85rem; font-weight: 600; text-transform: uppercase; color: var(--text-secondary); }}
    .tree-item {{
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 0.82rem;
      margin-top: 6px;
      cursor: pointer;
    }}
    button {{
      background-color: var(--bg-secondary);
      color: var(--text-primary);
      border: 1px solid var(--border-color);
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
    }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
</head>
<body>
  <header>
    <div style="display: flex; align-items: center;">
      <div class="logo-text">RepoGraph</div>
      <span class="stat-badge" id="stat-nodes">0 symbols</span>
      <span class="stat-badge" id="stat-edges">0 edges</span>
      <span class="stat-badge" id="stat-cycles">0 cycles</span>
    </div>
    <div>
      <input type="text" id="search" class="search-input" placeholder="Search symbols...">
      <button id="btn-fit">Fit Graph</button>
      <button id="btn-reset">Reset</button>
    </div>
  </header>

  <div class="layout-container">
    <div id="cy"></div>
    <aside class="inspector-drawer">
      <div>
        <h2 id="drawer-title" style="font-size: 1.15rem; word-break: break-word;">Select a Symbol</h2>
        <div id="drawer-file" style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px;">Click any node in graph</div>
      </div>
      <div class="score-card">
        <div>
          <div style="font-size: 0.8rem; color: var(--text-secondary); text-transform: uppercase;">Blast Radius</div>
          <div class="score-val score-green" id="score-value">--/100</div>
        </div>
        <div style="text-align: right; font-size: 0.85rem;">
          <div><strong id="count-callers">0</strong> callers</div>
          <div><strong id="count-files">0</strong> files</div>
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
          {{ selector: "node", style: {{ "label": "data(label)", "color": "#f0f6fc", "font-size": "11px", "background-color": "#58a6ff", "width": 24, "height": 24 }} }},
          {{ selector: 'node[kind = "class"]', style: {{ "background-color": "#bc8cff", "shape": "round-rectangle", "width": 30, "height": 30 }} }},
          {{ selector: 'node[kind = "interface"]', style: {{ "background-color": "#d29922", "shape": "diamond", "width": 28, "height": 28 }} }},
          {{ selector: "edge", style: {{ "width": 1.5, "line-color": "#30363d", "target-arrow-color": "#30363d", "target-arrow-shape": "triangle", "curve-style": "bezier", "opacity": 0.6 }} }},
          {{ selector: ".highlighted-target", style: {{ "background-color": "#f85149", "width": 36, "height": 36, "z-index": 999 }} }},
          {{ selector: ".highlighted-upstream", style: {{ "background-color": "#d29922", "line-color": "#d29922", "target-arrow-color": "#d29922", "opacity": 1.0 }} }},
          {{ selector: ".highlighted-downstream", style: {{ "background-color": "#58a6ff", "line-color": "#58a6ff", "target-arrow-color": "#58a6ff", "opacity": 1.0 }} }},
          {{ selector: ".dimmed", style: {{ "opacity": 0.12 }} }}
        ],
        layout: {{ name: "cose", animate: false }}
      }});

      cy.on("tap", "node", (evt) => {{
        const node = evt.target;
        const nId = node.data("id");
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
            li.textContent = `${{u.name}} (${{u.file_path}})`;
            uList.appendChild(li);
          }});

          const dList = document.getElementById("downstream-list");
          dList.innerHTML = "";
          rep.downstream_callees.forEach(d => {{
            const li = document.createElement("li");
            li.className = "tree-item";
            li.textContent = `${{d.name}} (${{d.file_path}})`;
            dList.appendChild(li);
          }});

          cy.elements().removeClass("highlighted-target highlighted-upstream highlighted-downstream dimmed").addClass("dimmed");
          node.removeClass("dimmed").addClass("highlighted-target");
          rep.upstream_callers.forEach(u => cy.getElementById(u.node_id).removeClass("dimmed").addClass("highlighted-upstream"));
          rep.downstream_callees.forEach(d => cy.getElementById(d.node_id).removeClass("dimmed").addClass("highlighted-downstream"));
        }}
      }});

      document.getElementById("btn-fit").addEventListener("click", () => cy.fit());
      document.getElementById("btn-reset").addEventListener("click", () => cy.elements().removeClass("highlighted-target highlighted-upstream highlighted-downstream dimmed"));
      document.getElementById("search").addEventListener("input", (e) => {{
        const q = e.target.value.toLowerCase().trim();
        if (!q) {{ cy.elements().removeClass("dimmed"); return; }}
        cy.elements().addClass("dimmed");
        const matched = cy.nodes().filter(n => (n.data("label")||"").toLowerCase().includes(q));
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
