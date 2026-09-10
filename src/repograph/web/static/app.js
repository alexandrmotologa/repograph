let cy = null;

async function initGraph() {
  try {
    const res = await fetch("/api/graph");
    const data = await res.json();

    document.getElementById("stat-nodes").textContent = `${data.total_nodes} symbols`;
    document.getElementById("stat-edges").textContent = `${data.total_edges} edges`;

    // Fetch cycles
    fetch("/api/cycles")
      .then(r => r.json())
      .then(cData => {
        const cBadge = document.getElementById("stat-cycles");
        cBadge.textContent = `${cData.total_cycles} cycles`;
        if (cData.total_cycles > 0) {
          cBadge.classList.add("cycles");
        }
      });

    cy = cytoscape({
      container: document.getElementById("cy"),
      elements: data.elements,
      style: [
        {
          selector: "node",
          style: {
            "label": "data(label)",
            "color": "#f0f6fc",
            "font-size": "11px",
            "text-valign": "bottom",
            "text-margin-y": "5px",
            "background-color": "#58a6ff",
            "border-width": 1,
            "border-color": "#30363d",
            "width": 24,
            "height": 24,
          }
        },
        {
          selector: 'node[kind = "class"]',
          style: {
            "background-color": "#bc8cff",
            "shape": "round-rectangle",
            "width": 30,
            "height": 30,
          }
        },
        {
          selector: 'node[kind = "interface"]',
          style: {
            "background-color": "#d29922",
            "shape": "diamond",
            "width": 28,
            "height": 28,
          }
        },
        {
          selector: 'node[kind = "module"]',
          style: {
            "background-color": "#30363d",
            "shape": "ellipse",
            "width": 18,
            "height": 18,
          }
        },
        {
          selector: "node[?is_entrypoint]",
          style: {
            "border-width": 3,
            "border-color": "#f85149",
          }
        },
        {
          selector: "edge",
          style: {
            "width": 1.5,
            "line-color": "#30363d",
            "target-arrow-color": "#30363d",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "opacity": 0.6,
          }
        },
        {
          selector: 'edge[edge_type = "IMPORTS"]',
          style: {
            "line-style": "dashed",
            "line-color": "#8b949e",
            "target-arrow-color": "#8b949e",
          }
        },
        {
          selector: ".highlighted-target",
          style: {
            "background-color": "#f85149",
            "border-color": "#fff",
            "border-width": 4,
            "width": 38,
            "height": 38,
            "z-index": 999,
          }
        },
        {
          selector: ".highlighted-upstream",
          style: {
            "background-color": "#d29922",
            "line-color": "#d29922",
            "target-arrow-color": "#d29922",
            "opacity": 1.0,
            "z-index": 900,
          }
        },
        {
          selector: ".highlighted-downstream",
          style: {
            "background-color": "#58a6ff",
            "line-color": "#58a6ff",
            "target-arrow-color": "#58a6ff",
            "opacity": 1.0,
            "z-index": 900,
          }
        },
        {
          selector: ".dimmed",
          style: {
            "opacity": 0.12,
          }
        }
      ],
      layout: {
        name: "cose",
        animate: false,
        randomize: false,
        componentSpacing: 100,
        nodeOverlap: 20,
        idealEdgeLength: 60,
      }
    });

    window.cy = cy;
    window.inspectSymbol = inspectSymbol;

    cy.on("tap", "node", function(evt) {
      const node = evt.target;
      inspectSymbol(node.data("id"), node.data("label"));
    });

    document.getElementById("btn-fit").addEventListener("click", () => cy.fit());
    document.getElementById("btn-reset").addEventListener("click", resetHighlight);

    // Search input
    const searchInput = document.getElementById("search");
    searchInput.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase().trim();
      if (!q) {
        cy.elements().removeClass("dimmed");
        return;
      }
      cy.elements().addClass("dimmed");
      const matched = cy.nodes().filter(n => {
        const label = (n.data("label") || "").toLowerCase();
        const qual = (n.data("qualified_name") || "").toLowerCase();
        return label.includes(q) || qual.includes(q);
      });
      matched.removeClass("dimmed");
      matched.connectedEdges().removeClass("dimmed");
    });

  } catch (err) {
    console.error("Failed to initialize graph:", err);
  }
}

async function inspectSymbol(nodeId, label) {
  try {
    const res = await fetch(`/api/blast-radius?symbol=${encodeURIComponent(nodeId)}`);
    const report = await res.json();

    document.getElementById("drawer-title").textContent = report.target_name || label;
    document.getElementById("drawer-file").textContent = report.target_file || nodeId;

    const scoreVal = document.getElementById("score-value");
    scoreVal.textContent = `${report.score}/100`;
    scoreVal.className = "score-val " + (report.score < 30 ? "score-green" : report.score < 70 ? "score-yellow" : "score-red");

    document.getElementById("count-callers").textContent = report.upstream_callers.length;
    document.getElementById("count-files").textContent = report.affected_files.length;
    document.getElementById("count-apis").textContent = report.affected_entrypoints.length;

    // Upstream list
    const upList = document.getElementById("upstream-list");
    upList.innerHTML = "";
    report.upstream_callers.slice(0, 15).forEach(node => {
      const li = document.createElement("li");
      li.className = "tree-item";
      li.innerHTML = `<strong>${node.name}</strong> <span style="color:#8b949e">(${node.file_path})</span>`;
      li.addEventListener("click", () => inspectSymbol(node.node_id, node.name));
      upList.appendChild(li);
    });

    // Downstream list
    const downList = document.getElementById("downstream-list");
    downList.innerHTML = "";
    report.downstream_callees.slice(0, 15).forEach(node => {
      const li = document.createElement("li");
      li.className = "tree-item";
      li.innerHTML = `<strong>${node.name}</strong> <span style="color:#8b949e">(${node.file_path})</span>`;
      li.addEventListener("click", () => inspectSymbol(node.node_id, node.name));
      downList.appendChild(li);
    });

    // Highlight in Cytoscape
    highlightBlastRadius(report);

  } catch (err) {
    console.error("Failed to inspect symbol:", err);
  }
}

function highlightBlastRadius(report) {
  if (!cy) return;

  cy.elements().removeClass("highlighted-target highlighted-upstream highlighted-downstream dimmed");
  cy.elements().addClass("dimmed");

  const targetNode = cy.getElementById(report.target_id);
  targetNode.removeClass("dimmed").addClass("highlighted-target");

  report.upstream_callers.forEach(node => {
    const el = cy.getElementById(node.node_id);
    el.removeClass("dimmed").addClass("highlighted-upstream");
    el.edgesWith(targetNode).removeClass("dimmed").addClass("highlighted-upstream");
  });

  report.downstream_callees.forEach(node => {
    const el = cy.getElementById(node.node_id);
    el.removeClass("dimmed").addClass("highlighted-downstream");
    targetNode.edgesWith(el).removeClass("dimmed").addClass("highlighted-downstream");
  });
}

function resetHighlight() {
  if (!cy) return;
  cy.elements().removeClass("highlighted-target highlighted-upstream highlighted-downstream dimmed");
}

window.addEventListener("DOMContentLoaded", initGraph);
