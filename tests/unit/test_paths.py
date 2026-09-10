"""Unit tests for call path tracing."""

from pathlib import Path

from repograph.config import ScanConfig
from repograph.graph.builder import GraphBuilder
from repograph.graph.paths import PathFinder
from repograph.parser.engine import ScannerEngine


def test_shortest_call_path():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)
    finder = PathFinder(graph)

    # Trace from OrderController.cancel_endpoint to OutboxRelay.dispatch
    result = finder.find_shortest_path("cancel_endpoint", "dispatch")
    assert result is not None
    assert result.total_hops >= 2
    assert result.source_name == "cancel_endpoint"
    assert result.target_name == "dispatch"
    assert len(result.steps) == result.total_hops

    # Test all simple paths
    all_paths = finder.find_all_paths("cancel_endpoint", "dispatch", max_paths=3)
    assert len(all_paths) >= 1

    # Nonexistent path
    none_res = finder.find_shortest_path("cancel_endpoint", "nonexistent_target")
    assert none_res is None
