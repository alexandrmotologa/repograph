"""Unit tests for RepoWatcher and RepoGraphShell components."""

from pathlib import Path

from repograph.shell import RepoGraphShell
from repograph.watcher import RepoWatcher


def test_watcher_initial_scan():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    watcher = RepoWatcher(fixture_dir)
    graph = watcher.initial_scan()
    assert graph.number_of_nodes() > 0
    # Single step check
    changed = watcher.check_changes_once()
    assert isinstance(changed, list)


def test_shell_initialization():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    shell = RepoGraphShell(fixture_dir)
    assert shell.graph.number_of_nodes() > 0
    assert shell.query is not None
    assert shell.path_finder is not None
