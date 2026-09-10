"""FastAPI local web server serving interactive codebase knowledge graph visualizer."""

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from repograph.analyzer.blast_radius import BlastRadiusCalculator
from repograph.analyzer.coupling import CouplingAnalyzer
from repograph.analyzer.cycles import CycleDetector
from repograph.analyzer.dead_code import DeadCodeHunter
from repograph.config import ScanConfig
from repograph.graph.builder import GraphBuilder
from repograph.graph.query import GraphQuery
from repograph.parser.engine import ScannerEngine


def create_app(root_dir: Path) -> FastAPI:
    """Create and configure FastAPI application for a repository."""
    app = FastAPI(title="RepoGraph Visualizer", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    config = ScanConfig(root_dir=root_dir)
    engine = ScannerEngine()
    builder = GraphBuilder()

    # Scan and build initial graph
    parsed_files = engine.scan_directory(config)
    graph = builder.build(parsed_files)
    query = GraphQuery(graph)
    calc = BlastRadiusCalculator(graph)
    cycle_det = CycleDetector(graph)
    dead_hunter = DeadCodeHunter(graph)
    coupling_analyzer = CouplingAnalyzer(graph)

    static_dir = Path(__file__).parent / "static"

    @app.get("/api/graph")
    def get_graph():
        """Retrieve full graph elements in Cytoscape format."""
        elements = query.to_cytoscape_elements()
        return {
            "elements": elements,
            "total_nodes": graph.number_of_nodes(),
            "total_edges": graph.number_of_edges(),
        }

    @app.get("/api/blast-radius")
    def get_blast_radius(symbol: str):
        """Compute blast radius for a symbol."""
        report = calc.calculate(symbol)
        return report.model_dump()

    @app.get("/api/cycles")
    def get_cycles():
        """Retrieve detected circular dependencies."""
        return cycle_det.detect_module_cycles().model_dump()

    @app.get("/api/dead-code")
    def get_dead_code():
        """Retrieve unreferenced dead code symbols."""
        return dead_hunter.find_dead_code().model_dump()

    @app.get("/api/metrics")
    def get_metrics():
        """Retrieve architectural coupling and health metrics."""
        return coupling_analyzer.compute_metrics().model_dump()

    @app.get("/", response_class=HTMLResponse)
    def index():
        html_file = static_dir / "index.html"
        if html_file.exists():
            return html_file.read_text(encoding="utf-8")
        return "<h1>RepoGraph Visualizer</h1><p>Static files missing.</p>"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


def run_server(root_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run uvicorn server for the repository."""
    app = create_app(root_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")
