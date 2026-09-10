"""Git diff analyzer mapping modified line ranges to affected AST symbols and blast radius."""

import re
import subprocess
from pathlib import Path

import networkx as nx
from pydantic import BaseModel, Field

from repograph.analyzer.blast_radius import BlastRadiusCalculator
from repograph.models import BlastRadiusReport, SymbolKind, SymbolNode


class ChangedFileDiff(BaseModel):
    """File modified in Git with set of changed line numbers."""

    file_path: str
    modified_lines: list[int] = Field(default_factory=list)


class GitDiffResult(BaseModel):
    """Aggregated blast radius assessment for a Git changeset or Pull Request."""

    base_ref: str
    changed_files_count: int
    directly_modified_symbols: list[SymbolNode] = Field(default_factory=list)
    total_impacted_symbols: int = 0
    aggregate_score: float = 0.0
    affected_files: list[str] = Field(default_factory=list)
    affected_entrypoints: list[str] = Field(default_factory=list)
    affected_tests: list[str] = Field(default_factory=list)
    symbol_reports: list[BlastRadiusReport] = Field(default_factory=list)


class GitDiffAnalyzer:
    """Parses Git diff output, identifies affected symbols, and computes PR-wide blast radius."""

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph
        self.calc = BlastRadiusCalculator(graph)

    def parse_diff_text(self, diff_text: str) -> list[ChangedFileDiff]:
        """Parse raw unified diff output to extract changed line numbers per file."""
        files: list[ChangedFileDiff] = []
        current_file = None
        current_lines: set[int] = set()

        # Regex for diff file header: diff --git a/path b/path
        file_re = re.compile(r"^diff --git a/.*? b/(.*)$")
        # Regex for hunk: @@ -l,s +start,count @@
        hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

        for line in diff_text.splitlines():
            f_match = file_re.match(line)
            if f_match:
                if current_file and current_lines:
                    files.append(
                        ChangedFileDiff(
                            file_path=current_file, modified_lines=sorted(list(current_lines))
                        )
                    )
                current_file = f_match.group(1)
                current_lines = set()
                continue

            h_match = hunk_re.match(line)
            if h_match and current_file:
                start_line = int(h_match.group(1))
                count = int(h_match.group(2)) if h_match.group(2) is not None else 1
                for l_num in range(start_line, start_line + max(1, count)):
                    current_lines.add(l_num)

        if current_file and current_lines:
            files.append(
                ChangedFileDiff(file_path=current_file, modified_lines=sorted(list(current_lines)))
            )

        return files

    def run_git_diff(
        self, repo_dir: Path, base_ref: str | None = None, staged: bool = False
    ) -> str:
        """Execute git diff command and return text."""
        cmd = ["git", "diff", "--unified=0"]
        if staged:
            cmd.append("--staged")
        elif base_ref:
            cmd.append(base_ref)

        try:
            res = subprocess.run(
                cmd,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            return res.stdout
        except Exception:
            return ""

    def analyze_diff(
        self,
        repo_dir: Path,
        base_ref: str = "HEAD~1",
        staged: bool = False,
        raw_diff: str | None = None,
    ) -> GitDiffResult:
        """Identify modified AST symbols and aggregate their cumulative blast radius."""
        diff_text = (
            raw_diff
            if raw_diff is not None
            else self.run_git_diff(repo_dir, base_ref=base_ref, staged=staged)
        )
        changed_files = self.parse_diff_text(diff_text)

        directly_modified: list[SymbolNode] = []
        seen_sym_ids: set[str] = set()

        for cf in changed_files:
            # Find symbols in this file whose line range intersects modified lines
            norm_file = cf.file_path.replace("\\", "/")
            for node_id, data in self.graph.nodes(data=True):
                if (
                    data.get("file_path") == norm_file
                    and data.get("kind") != SymbolKind.MODULE.value
                ):
                    s_start = data.get("line_start", 1)
                    s_end = data.get("line_end", 1)

                    if any(s_start <= l_num <= s_end for l_num in cf.modified_lines):
                        if node_id not in seen_sym_ids:
                            seen_sym_ids.add(node_id)
                            directly_modified.append(
                                SymbolNode(
                                    id=node_id,
                                    name=data.get("name", node_id),
                                    qualified_name=data.get("qualified_name", node_id),
                                    kind=SymbolKind(data.get("kind", SymbolKind.FUNCTION.value)),
                                    file_path=norm_file,
                                    line_start=s_start,
                                    line_end=s_end,
                                    complexity=data.get("complexity", 1),
                                    is_exported=data.get("is_exported", False),
                                    is_entrypoint=data.get("is_entrypoint", False),
                                )
                            )

        # Calculate blast radius for each modified symbol
        all_reports: list[BlastRadiusReport] = []
        all_affected_files: set[str] = {cf.file_path for cf in changed_files}
        all_affected_entrypoints: set[str] = set()
        all_affected_tests: set[str] = set()
        all_impacted_symbols: set[str] = set(seen_sym_ids)
        total_score = 0.0

        for sym in directly_modified:
            rep = self.calc.calculate(sym.id)
            all_reports.append(rep)
            total_score = max(total_score, rep.score)
            all_affected_files.update(rep.affected_files)
            all_affected_entrypoints.update(rep.affected_entrypoints)
            all_affected_tests.update(rep.affected_tests)
            for u in rep.upstream_callers:
                all_impacted_symbols.add(u.node_id)
            for d in rep.downstream_callees:
                all_impacted_symbols.add(d.node_id)

        # Boost score if multiple critical components are modified at once
        if len(directly_modified) > 1:
            total_score = min(100.0, round(total_score * (1.0 + (0.1 * len(directly_modified))), 1))

        return GitDiffResult(
            base_ref=base_ref if not staged else "--staged",
            changed_files_count=len(changed_files),
            directly_modified_symbols=directly_modified,
            total_impacted_symbols=len(all_impacted_symbols),
            aggregate_score=total_score,
            affected_files=sorted(list(all_affected_files)),
            affected_entrypoints=sorted(list(all_affected_entrypoints)),
            affected_tests=sorted(list(all_affected_tests)),
            symbol_reports=all_reports,
        )
