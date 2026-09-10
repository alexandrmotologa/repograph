"""Unit tests for circular dependencies, dead code, and coupling analyzers."""

from pathlib import Path

from repograph.analyzer.coupling import CouplingAnalyzer
from repograph.analyzer.cycles import CycleDetector
from repograph.analyzer.dead_code import DeadCodeHunter
from repograph.config import ScanConfig
from repograph.graph.builder import GraphBuilder
from repograph.parser.engine import ScannerEngine


def test_circular_dependency_detection():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)
    detector = CycleDetector(graph)

    report = detector.detect_module_cycles()
    assert report.total_cycles >= 1
    # Check that alpha and beta are in the cycle loop
    cycle_files = " ".join(report.cycles[0].files)
    assert "alpha" in cycle_files and "beta" in cycle_files

    # Test symbol cycles
    sym_report = detector.detect_symbol_cycles()
    assert sym_report is not None


def test_graph_exporter():
    from repograph.export import GraphExporter

    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)
    builder = GraphBuilder()
    graph = builder.build(parsed_files)

    exporter = GraphExporter(graph)
    dot_output = exporter.to_dot()
    assert "digraph RepoGraph" in dot_output
    assert "->" in dot_output

    from repograph.analyzer.blast_radius import BlastRadiusCalculator

    calc = BlastRadiusCalculator(graph)
    report = calc.calculate("Order.cancel")
    mermaid_blast = exporter.export_blast_radius_mermaid(report)
    assert "flowchart TD" in mermaid_blast
    assert "TARGET" in mermaid_blast


def test_dead_code_detection():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)
    hunter = DeadCodeHunter(graph)

    report = hunter.find_dead_code(include_exported=True)
    dead_names = [d.name for d in report.dead_symbols]

    assert "orphan_tax_calculator" in dead_names or "unused_legacy_serializer" in dead_names


def test_coupling_metrics():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)
    analyzer = CouplingAnalyzer(graph)

    metrics = analyzer.compute_metrics()
    assert metrics.total_files > 0
    assert metrics.total_symbols > 0
    assert len(metrics.modules_coupling) > 0
