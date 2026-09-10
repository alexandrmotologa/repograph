"""Integration tests for Typer CLI commands."""

from pathlib import Path

from typer.testing import CliRunner

from repograph.cli import app

runner = CliRunner()
FIXTURE_DIR = str(Path(__file__).parent.parent / "fixtures" / "python_app")


def test_cli_scan():
    result = runner.invoke(app, ["scan", FIXTURE_DIR])
    assert result.exit_code == 0
    assert "Repository Code Graph Summary" in result.stdout
    assert "Scanned Source Files" in result.stdout


def test_cli_blast_radius():
    result = runner.invoke(app, ["blast-radius", "Order.cancel", "--dir", FIXTURE_DIR])
    assert result.exit_code == 0
    assert "Blast Radius Impact Report" in result.stdout
    assert "Blast Radius Score:" in result.stdout


def test_cli_cycles():
    result = runner.invoke(app, ["cycles", "--dir", FIXTURE_DIR])
    assert result.exit_code == 0
    assert "circular dependency" in result.stdout.lower()


def test_cli_dead_code():
    result = runner.invoke(app, ["dead-code", "--dir", FIXTURE_DIR, "--include-exported"])
    assert result.exit_code == 0
    assert "Dead Code Candidates" in result.stdout


def test_cli_metrics():
    result = runner.invoke(app, ["metrics", "--dir", FIXTURE_DIR])
    assert result.exit_code == 0
    assert "Codebase Architectural Metrics" in result.stdout


def test_cli_export_mermaid():
    result = runner.invoke(app, ["export", "--dir", FIXTURE_DIR, "--format", "mermaid"])
    assert result.exit_code == 0
    assert "flowchart TD" in result.stdout


def test_cli_export_json():
    result = runner.invoke(app, ["export", "--dir", FIXTURE_DIR, "--format", "json"])
    assert result.exit_code == 0
    assert '"nodes"' in result.stdout
