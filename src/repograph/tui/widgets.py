"""Textual widgets for displaying symbol cards, metrics, and call hierarchy trees."""

from pathlib import Path

from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static, Tree

from repograph.models import BlastRadiusReport, SymbolNode


class SymbolDetailsWidget(Static):
    """Displays detailed metadata, complexity score, and source code snippet for a symbol."""

    def update_symbol(
        self, sym: SymbolNode, root_dir: Path, report: BlastRadiusReport | None = None
    ) -> None:
        """Render symbol details card."""
        info_lines = [
            f"[bold cyan]{sym.qualified_name}[/bold cyan] ([italic magenta]{sym.kind.value}[/italic magenta])",
            f"[bold]Location:[/bold] {sym.location_str}",
            f"[bold]Parameters:[/bold] {', '.join(sym.parameters) if sym.parameters else 'none'}",
            f"[bold]Complexity:[/bold] {sym.complexity}",
            f"[bold]Exported:[/bold] {'Yes' if sym.is_exported else 'No'} | [bold]Entrypoint:[/bold] {'Yes' if sym.is_entrypoint else 'No'}",
        ]

        if report:
            score_col = "green" if report.score < 30 else ("yellow" if report.score < 70 else "red")
            info_lines.append(
                f"[bold]Blast Radius Score:[/bold] [{score_col}]{report.score}/100[/{score_col}] "
                f"({len(report.upstream_callers)} callers, {len(report.affected_files)} files)"
            )

        if sym.docstring:
            info_lines.append(f"\n[italic dim]{sym.docstring}[/italic dim]")

        # Attempt to read source preview
        snippet = ""
        try:
            full_path = root_dir / sym.file_path
            if full_path.exists():
                lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
                start = max(0, sym.line_start - 1)
                end = min(len(lines), sym.line_end)
                code_text = "\n".join(lines[start:end])
                snippet = f"\n\n[bold]Source Preview:[/bold]\n```\n{code_text}\n```"
        except Exception:
            pass

        full_content = "\n".join(info_lines) + snippet
        self.update(
            Panel(Text.from_markup(full_content), title="Symbol Inspector", border_style="cyan")
        )


class CallHierarchyTree(Tree):
    """Interactive tree widget rendering upstream callers and downstream callees."""

    def populate_hierarchy(self, report: BlastRadiusReport) -> None:
        """Populate tree with blast radius results."""
        self.clear()
        self.root.label = f"Target: [bold cyan]{report.target_name}[/bold cyan]"

        up_branch = self.root.add(
            f"[bold red][^] Upstream Callers ({len(report.upstream_callers)})[/bold red]", expand=True
        )
        for node in report.upstream_callers:
            badge = f"[{node.category.value}]"
            col = (
                "red"
                if node.category.value == "CRITICAL"
                else ("blue" if node.category.value == "TEST" else "yellow")
            )
            up_branch.add_leaf(
                f"[{col}]{badge}[/{col}] {node.name} [dim]({Path(node.file_path).name})[/dim]"
            )

        down_branch = self.root.add(
            f"[bold green][v] Downstream Dependencies ({len(report.downstream_callees)})[/bold green]",
            expand=True,
        )
        for node in report.downstream_callees:
            down_branch.add_leaf(f"{node.name} [dim]({Path(node.file_path).name})[/dim]")
