"""Filesystem watcher for incremental live graph updates during development."""

import logging
import time
from collections.abc import Callable
from pathlib import Path

import networkx as nx

from repograph.config import ScanConfig
from repograph.graph.builder import GraphBuilder
from repograph.graph.cache import GraphCache
from repograph.models import ParsedFile
from repograph.parser.engine import ScannerEngine

logger = logging.getLogger(__name__)


class RepoWatcher:
    """Watches a repository for file changes and triggers sub-second incremental graph updates."""

    def __init__(
        self,
        root_dir: Path,
        on_change: Callable[[list[str], nx.DiGraph], None] | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        self.root_dir = root_dir.resolve()
        self.config = ScanConfig(root_dir=self.root_dir)
        self.engine = ScannerEngine()
        self.builder = GraphBuilder()
        self.cache = GraphCache(self.root_dir / self.config.cache_dir)
        self.on_change = on_change
        self.poll_interval = poll_interval
        self._running = False
        self._file_mtimes: dict[str, float] = {}
        self._parsed_files: dict[str, ParsedFile] = {}
        self.graph: nx.DiGraph = nx.DiGraph()

    def initial_scan(self) -> nx.DiGraph:
        """Perform first scan and record file timestamps."""
        self._parsed_files = self.engine.scan_directory(self.config)
        self.cache.save(self._parsed_files)
        self.graph = self.builder.build(self._parsed_files)

        files = self.engine.discover_files(self.root_dir, self.config)
        for f in files:
            rel = f.relative_to(self.root_dir).as_posix()
            try:
                self._file_mtimes[rel] = f.stat().st_mtime
            except OSError:
                pass

        return self.graph

    def check_changes_once(self) -> list[str]:
        """Check for changed files since last check and update graph if modified."""
        current_files = self.engine.discover_files(self.root_dir, self.config)
        current_map: dict[str, Path] = {
            f.relative_to(self.root_dir).as_posix(): f for f in current_files
        }

        changed_rel_paths: list[str] = []

        # 1. Check modified or newly created files
        for rel_path, full_path in current_map.items():
            try:
                mtime = full_path.stat().st_mtime
                old_mtime = self._file_mtimes.get(rel_path)
                if old_mtime is None or mtime > old_mtime:
                    self._file_mtimes[rel_path] = mtime
                    changed_rel_paths.append(rel_path)
                    # Re-parse changed file
                    pf = self.engine.scan_file(full_path, self.root_dir, self.config)
                    if pf:
                        self._parsed_files[rel_path] = pf
            except OSError:
                pass

        # 2. Check deleted files
        deleted_paths = [p for p in self._file_mtimes if p not in current_map]
        for dp in deleted_paths:
            del self._file_mtimes[dp]
            self._parsed_files.pop(dp, None)
            changed_rel_paths.append(dp)

        if changed_rel_paths:
            self.graph = self.builder.build(self._parsed_files)
            self.cache.save(self._parsed_files)
            if self.on_change:
                self.on_change(changed_rel_paths, self.graph)

        return changed_rel_paths

    def watch(self) -> None:
        """Start blocking watch loop."""
        self.initial_scan()
        self._running = True
        try:
            while self._running:
                time.sleep(self.poll_interval)
                self.check_changes_once()
        except KeyboardInterrupt:
            self._running = False

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
