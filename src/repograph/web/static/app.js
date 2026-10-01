let cy = null;
let currentFilter = "all";
let currentLayoutIndex = 0;
const layoutOptions = [
  { name: "cose", animate: false, randomize: false, componentSpacing: 90, nodeOverlap: 20, idealEdgeLength: 60 },
  { name: "concentric", minNodeSpacing: 60, animate: false },
  { name: "breadthfirst", directed: true, spacingFactor: 1.25, animate: false },
  { name: "circle", animate: false }
];

async function initGraph() {
  try {
    const res = await fetch("/api/graph");
    const data = await res.json();

    document.getElementById("stat-nodes").textContent = `${data.total_nodes} symbols`;
    document.getElementById("stat-edges").textContent = `${data.total_edges} edges`;

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
            "font-family": "Inter, sans-serif",
            "font-size": "11px",
            "font-weight": 500,
            "text-valign": "bottom",
            "text-margin-y": "6px",
            "background-color": "#38bdf8",
            "border-width": 1.5,
            "border-color": "rgba(255, 255, 255, 0.15)",
            "width": 26,
            "height": 26,
            "transition-property": "background-color, border-color, width, height, opacity",
            "transition-duration": "0.2s"
          }
        },
        {
          selector: 'node[kind = "class"]',
          style: {
            "background-color": "#c084fc",
            "shape": "round-rectangle",
            "width": 32,
            "height": 32,
          }
        },
        {
          selector: 'node[kind = "interface"]',
          style: {
            "background-color": "#fbbf24",
            "shape": "diamond",
            "width": 30,
            "height": 30,
          }
        },
        {
          selector: 'node[kind = "module"]',
          style: {
            "background-color": "#475569",
            "shape": "ellipse",
            "width": 20,
            "height": 20,
          }
        },
        {
          selector: "node[?is_entrypoint]",
          style: {
            "border-width": 3,
            "border-color": "#f87171",
          }
        },
        {
          selector: "edge",
          style: {
            "width": 1.5,
            "line-color": "#334155",
            "target-arrow-color": "#334155",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.8,
            "curve-style": "bezier",
            "opacity": 0.65,
            "transition-property": "line-color, target-arrow-color, opacity, width",
            "transition-duration": "0.2s"
          }
        },
        {
          selector: 'edge[edge_type = "IMPORTS"]',
          style: {
            "line-style": "dashed",
            "line-color": "#64748b",
            "target-arrow-color": "#64748b",
          }
        },
        {
          selector: 'edge[edge_type = "EXTENDS"], edge[edge_type = "IMPLEMENTS"]',
          style: {
            "line-color": "#c084fc",
            "target-arrow-color": "#c084fc",
            "width": 2,
          }
        },
        {
          selector: ".highlighted-target",
          style: {
            "background-color": "#f87171",
            "border-color": "#ffffff",
            "border-width": 3.5,
            "width": 40,
            "height": 40,
            "z-index": 999,
          }
        },
        {
          selector: ".highlighted-upstream",
          style: {
            "background-color": "#fbbf24",
            "line-color": "#fbbf24",
            "target-arrow-color": "#fbbf24",
            "opacity": 1.0,
            "width": 32,
            "height": 32,
            "z-index": 900,
          }
        },
        {
          selector: ".highlighted-downstream",
          style: {
            "background-color": "#38bdf8",
            "line-color": "#38bdf8",
            "target-arrow-color": "#38bdf8",
            "opacity": 1.0,
            "width": 32,
            "height": 32,
            "z-index": 900,
          }
        },
        {
          selector: ".dimmed",
          style: {
            "opacity": 0.12,
          }
        },
        {
          selector: ".filtered-out",
          style: {
            "display": "none"
          }
        }
      ],
      layout: layoutOptions[0]
    });

    window.cy = cy;
    window.inspectSymbol = inspectSymbol;

    cy.on("tap", "node", function(evt) {
      const node = evt.target;
      inspectSymbol(node.data("id"), node.data("label"), node.data("kind"));
    });

    document.getElementById("btn-fit").addEventListener("click", () => cy.fit(undefined, 30));
    document.getElementById("btn-reset").addEventListener("click", resetHighlight);

    // Layout switch button
    document.getElementById("btn-layout").addEventListener("click", () => {
      currentLayoutIndex = (currentLayoutIndex + 1) % layoutOptions.length;
      const opt = layoutOptions[currentLayoutIndex];
      cy.layout(opt).run();
    });

    // PNG export button
    document.getElementById("btn-export-png").addEventListener("click", () => {
      const png64 = cy.png({ full: true, scale: 2, bg: "#090d13" });
      const a = document.createElement("a");
      a.href = png64;
      a.download = "repograph-graph.png";
      a.click();
    });

    // Filter toolbar buttons
    document.querySelectorAll(".filter-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentFilter = btn.dataset.filter;
        applyFilter(currentFilter);
      });
    });

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
        const file = (n.data("file_path") || "").toLowerCase();
        return label.includes(q) || qual.includes(q) || file.includes(q);
      });
      matched.removeClass("dimmed");
      matched.connectedEdges().removeClass("dimmed");
    });

    // Keyboard shortcuts
    window.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement !== searchInput) {
        e.preventDefault();
        searchInput.focus();
      } else if (e.key === "Escape") {
        resetHighlight();
        searchInput.blur();
      } else if (e.key.toLowerCase() === "f" && document.activeElement !== searchInput) {
        cy.fit(undefined, 30);
      }
    });

  } catch (err) {
    console.error("Failed to initialize graph:", err);
  }
}

function applyFilter(filterType) {
  if (!cy) return;
  cy.nodes().removeClass("filtered-out");
  if (filterType === "all") return;

  cy.nodes().forEach(n => {
    const kind = n.data("kind");
    const isEntry = n.data("is_entrypoint");
    if (filterType === "entrypoint") {
      if (!isEntry) n.addClass("filtered-out");
    } else if (kind !== filterType) {
      n.addClass("filtered-out");
    }
  });
}

async function inspectSymbol(nodeId, label, kind) {
  try {
    const res = await fetch(`/api/blast-radius?symbol=${encodeURIComponent(nodeId)}`);
    const report = await res.json();

    document.getElementById("drawer-kind").textContent = kind || "SYMBOL";
    document.getElementById("drawer-title").textContent = report.target_name || label;
    document.getElementById("drawer-file").textContent = report.target_file || nodeId;

    const scoreVal = document.getElementById("score-value");
    scoreVal.textContent = `${report.score}/100`;
    scoreVal.className = "score-val " + (report.score < 30 ? "score-green" : report.score < 70 ? "score-yellow" : "score-red");

    document.getElementById("count-callers").textContent = report.upstream_callers.length;
    document.getElementById("count-files").textContent = report.affected_files.length;
    document.getElementById("count-apis").textContent = report.affected_entrypoints.length;

    document.getElementById("upstream-count-pill").textContent = report.upstream_callers.length;
    document.getElementById("downstream-count-pill").textContent = report.downstream_callees.length;

    // Upstream list
    const upList = document.getElementById("upstream-list");
    upList.innerHTML = "";
    if (report.upstream_callers.length === 0) {
      upList.innerHTML = '<li class="tree-empty">No upstream callers (entrypoint or leaf).</li>';
    } else {
      report.upstream_callers.slice(0, 15).forEach(node => {
        const li = document.createElement("li");
        li.className = "tree-item";
        li.innerHTML = `<span class="name">${node.name}</span><span class="path">${node.file_path}</span>`;
        li.addEventListener("click", () => inspectSymbol(node.node_id, node.name, node.kind));
        upList.appendChild(li);
      });
    }

    // Downstream list
    const downList = document.getElementById("downstream-list");
    downList.innerHTML = "";
    if (report.downstream_callees.length === 0) {
      downList.innerHTML = '<li class="tree-empty">No downstream dependencies.</li>';
    } else {
      report.downstream_callees.slice(0, 15).forEach(node => {
        const li = document.createElement("li");
        li.className = "tree-item";
        li.innerHTML = `<span class="name">${node.name}</span><span class="path">${node.file_path}</span>`;
        li.addEventListener("click", () => inspectSymbol(node.node_id, node.name, node.kind));
        downList.appendChild(li);
      });
    }

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
