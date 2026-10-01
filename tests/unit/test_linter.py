"""Unit tests for declarative configuration loader and architectural linter."""

from pathlib import Path

from repograph.analyzer.linter import ArchitecturalLinter
from repograph.config import ArchitecturalRules, ForbiddenImportRule, load_config
from repograph.graph.builder import GraphBuilder
from repograph.parser.engine import ScannerEngine


def test_load_config_from_toml(tmp_path):
    toml_content = """
ignored_dirs = ["custom_dir"]
max_file_size_bytes = 1048576

[rules]
max_complexity = 12
max_risk_gate = 50.0

[[rules.forbidden_imports]]
from = "domain/*"
to = "controllers/*"
message = "Domain must not import Controllers"
severity = "error"

[[rules.max_instability]]
module = "core"
max_i = 0.4
"""
    config_file = tmp_path / "repograph.toml"
    config_file.write_text(toml_content, encoding="utf-8")

    cfg = load_config(tmp_path)
    assert "custom_dir" in cfg.ignored_dirs
    assert cfg.max_file_size_bytes == 1048576
    assert cfg.rules.max_complexity == 12
    assert cfg.rules.max_risk_gate == 50.0
    assert len(cfg.rules.forbidden_imports) == 1
    assert cfg.rules.forbidden_imports[0].from_pattern == "domain/*"
    assert len(cfg.rules.instability_rules) == 1


def test_architectural_linter_forbidden_imports():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    engine = ScannerEngine()
    config = load_config(fixture_dir)
    parsed_files = engine.scan_directory(config)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)

    # Define a forbidden import rule: controllers should not directly import infra
    rules = ArchitecturalRules(
        forbidden_imports=[
            ForbiddenImportRule(
                from_pattern="controllers/*",
                to_pattern="infra/*",
                message="Controllers must not directly depend on infra",
                severity="error",
            )
        ]
    )

    linter = ArchitecturalLinter(graph, rules)
    report = linter.lint()
    assert report is not None
    # In python_app fixture, controllers imports services and models, not infra directly
    assert report.is_clean

    # Define a violation rule: services should not import models (in fixture, order_service imports models/order)
    failing_rules = ArchitecturalRules(
        forbidden_imports=[
            ForbiddenImportRule(
                from_pattern="services/*",
                to_pattern="models/*",
                message="Services must not import models",
                severity="error",
            )
        ]
    )
    failing_linter = ArchitecturalLinter(graph, failing_rules)
    failing_report = failing_linter.lint()
    assert failing_report.total_violations >= 1
    assert not failing_report.is_clean
    assert any("Services must not import models" in v.message for v in failing_report.violations)
