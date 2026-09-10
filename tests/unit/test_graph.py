"""Unit tests for knowledge graph builder and query engine."""

from pathlib import Path

from repograph.config import ScanConfig
from repograph.graph.builder import GraphBuilder
from repograph.graph.cache import GraphCache
from repograph.graph.query import GraphQuery
from repograph.parser.engine import ScannerEngine


def test_graph_builder_and_query(tmp_path):
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)

    assert graph.number_of_nodes() > 5
    assert graph.number_of_edges() > 0

    query = GraphQuery(graph)
    results = query.find_symbols("cancel")
    assert len(results) > 0
    assert any("cancel" in r["name"].lower() for r in results)

    # Test Cytoscape serialization
    elements = query.to_cytoscape_elements()
    assert len(elements) == graph.number_of_nodes() + graph.number_of_edges()

    # Test get_node
    first_node_id = list(graph.nodes)[0]
    node_data = query.get_node(first_node_id)
    assert node_data is not None
    assert node_data["id"] == first_node_id
    assert query.get_node("invalid_id") is None

    # Test get_subgraph
    sub = query.get_subgraph(first_node_id, upstream_depth=1, downstream_depth=1)
    assert first_node_id in sub.nodes
    assert query.get_subgraph("nonexistent_node").number_of_nodes() == 0


def test_graph_cache(tmp_path):
    cache = GraphCache(tmp_path / ".repograph")
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    cache.save(parsed_files)
    loaded_files, hashes = cache.load()

    assert len(loaded_files) == len(parsed_files)
    assert len(hashes) == len(parsed_files)
