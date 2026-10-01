"""Unit tests for SARIF 2.1.0 static analysis report exporter."""

import json
from pathlib import Path

from repograph.config import load_config
from repograph.export_sarif import SarifExporter
from repograph.graph.builder import GraphBuilder
from repograph.parser.engine import ScannerEngine


def test_sarif_export():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    engine = ScannerEngine()
    config = load_config(fixture_dir)
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)

    exporter = SarifExporter(graph, rules=config.rules)
    sarif_json_str = exporter.to_json()
    sarif_data = json.loads(sarif_json_str)

    assert sarif_data["version"] == "2.1.0"
    assert "$schema" in sarif_data
    assert len(sarif_data["runs"]) == 1
    run = sarif_data["runs"][0]
    assert run["tool"]["driver"]["name"] == "RepoGraph"

    # Verify results contain dead code or cycle issues
    rule_ids = {r["ruleId"] for r in run["results"]}
    assert "RG001" in rule_ids or "RG002" in rule_ids
