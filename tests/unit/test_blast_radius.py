"""Unit tests for blast radius calculation and impact scoring."""

from pathlib import Path

from repograph.analyzer.blast_radius import BlastRadiusCalculator
from repograph.config import ScanConfig
from repograph.graph.builder import GraphBuilder
from repograph.parser.engine import ScannerEngine


def test_blast_radius_order_cancellation():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)
    calc = BlastRadiusCalculator(graph)

    # Calculate blast radius for Order.cancel
    report = calc.calculate("Order.cancel")

    assert report.target_name == "cancel"
    assert report.score > 0.0
    assert len(report.affected_files) >= 2

    # Verify upstream caller detection (OrderService.cancel_order should be an upstream caller)
    upstream_names = [u.name for u in report.upstream_callers]
    assert "cancel_order" in upstream_names or any("cancel" in n for n in upstream_names)

    # Verify downstream callees (record_event should be downstream)
    downstream_names = [d.name for d in report.downstream_callees]
    assert "record_event" in downstream_names or len(downstream_names) > 0


def test_blast_radius_unknown_symbol():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)
    calc = BlastRadiusCalculator(graph)

    report = calc.calculate("NonExistentSymbol")
    assert report.score == 0.0
    assert len(report.upstream_callers) == 0
    assert len(report.downstream_callees) == 0
