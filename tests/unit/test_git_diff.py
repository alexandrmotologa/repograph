"""Unit tests for Git diff hunk parsing and PR blast radius calculation."""

from pathlib import Path

from repograph.analyzer.git_diff import GitDiffAnalyzer
from repograph.config import ScanConfig
from repograph.graph.builder import GraphBuilder
from repograph.parser.engine import ScannerEngine

MOCK_DIFF = """diff --git a/models/order.py b/models/order.py
index 1111111..2222222 100644
--- a/models/order.py
+++ b/models/order.py
@@ -15,2 +15,3 @@ class Order:
     def cancel(self) -> None:
+        # Added check
         if self.status == "COMPLETED":
"""


def test_git_diff_parser():
    analyzer = GitDiffAnalyzer(None)
    changed = analyzer.parse_diff_text(MOCK_DIFF)
    assert len(changed) == 1
    assert changed[0].file_path == "models/order.py"
    assert 15 in changed[0].modified_lines


def test_git_diff_analysis_on_graph():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    config = ScanConfig(root_dir=fixture_dir)
    engine = ScannerEngine()
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)
    analyzer = GitDiffAnalyzer(graph)

    res = analyzer.analyze_diff(fixture_dir, raw_diff=MOCK_DIFF)
    assert res.changed_files_count == 1
    assert len(res.directly_modified_symbols) >= 1
    assert any("cancel" in s.name for s in res.directly_modified_symbols)
    assert res.aggregate_score > 0.0
    assert len(res.affected_files) >= 1
