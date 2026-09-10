"""Unit tests for standalone HTML report generation."""

from pathlib import Path

from repograph.config import ScanConfig
from repograph.export_html import HtmlReportGenerator
from repograph.graph.builder import GraphBuilder
from repograph.parser.engine import ScannerEngine


def test_html_report_generation(tmp_path):
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)
    generator = HtmlReportGenerator(graph)

    out_file = tmp_path / "report.html"
    res_path = generator.export_to_file(out_file, title="Custom Test Report")

    assert res_path.exists()
    content = res_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Custom Test Report" in content
    assert "cytoscape" in content
    assert "DATA =" in content
