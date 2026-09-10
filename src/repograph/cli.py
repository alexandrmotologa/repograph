"""RepoGraph Command-Line Interface powered by Typer and Rich."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from repograph import __version__
from repograph.analyzer.blast_radius import BlastRadiusCalculator
from repograph.analyzer.coupling import CouplingAnalyzer
from repograph.analyzer.cycles import CycleDetector
from repograph.analyzer.dead_code import DeadCodeHunter
from repograph.config import ScanConfig
from repograph.export import GraphExporter
from repograph.graph.builder import GraphBuilder
from repograph.graph.cache import GraphCache
from repograph.parser.engine import ScannerEngine

app = typer.Typer(
    name="repograph",
    help="RepoGraph: Local-First Codebase Knowledge Graph & Blast-Radius Engine",
    add_completion=False,
)
console = Console()


def _build_graph_for_dir(target_dir: Path, use_cache: bool = True):
    """Internal helper to scan directory and construct the graph."""
    config = ScanConfig(root_dir=target_dir.resolve())
    engine = ScannerEngine()
    cache = GraphCache(config.root_dir / config.cache_dir)

    cached_files, cached_hashes = ({}, {})
    if use_cache:
        cached_files, cached_hashes = cache.load()

    # Discover and scan
    parsed_files = engine.scan_directory(config, existing_hashes=cached_hashes)

    # Save to cache if enabled
    if use_cache and parsed_files:
        cache.save(parsed_files)

    builder = GraphBuilder()
    graph = builder.build(parsed_files)
    return graph, parsed_files


@app.command()
def scan(
    directory: Path = typer.Argument(Path("."), help="Path to repository to scan"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass and rebuild graph cache"),
):
    """Scan repository and print codebase knowledge graph statistics."""
    console.print(
        f"[bold cyan]RepoGraph v{__version__}[/bold cyan] scanning [green]{directory}[/green]..."
    )

    graph, parsed_files = _build_graph_for_dir(directory, use_cache=not no_cache)

    # Health checks
    cycle_det = CycleDetector(graph)
    module_cycles = cycle_det.detect_module_cycles()
    dead_hunter = DeadCodeHunter(graph)
    dead_code = dead_hunter.find_dead_code()

    # Summary table
    table = Table(
        title="Repository Code Graph Summary", show_header=True, header_style="bold magenta"
    )
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Scanned Source Files", str(len(parsed_files)))
    table.add_row("Extracted Symbol Nodes", str(graph.number_of_nodes()))
    table.add_row("Graph Dependency Edges", str(graph.number_of_edges()))
    table.add_row(
        "Circular Import Loops",
        f"[red]{module_cycles.total_cycles}[/red]"
        if module_cycles.total_cycles > 0
        else "[green]0[/green]",
    )
    table.add_row(
        "Unreferenced Dead Symbols",
        f"[yellow]{dead_code.total_dead}[/yellow]"
        if dead_code.total_dead > 0
        else "[green]0[/green]",
    )

    console.print(table)


@app.command()
def blast_radius(
    symbol: str = typer.Argument(
        ..., help="Symbol name or qualified name (e.g. 'OrderService.cancel')"
    ),
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Repository path"),
    depth: int = typer.Option(10, "--depth", help="Maximum traversal depth"),
):
    """Calculate the upstream callers and downstream side-effects of a symbol change."""
    graph, _ = _build_graph_for_dir(directory)
    calc = BlastRadiusCalculator(graph)
    report = calc.calculate(symbol, max_depth=depth)

    if not report.target_file and report.score == 0.0:
        console.print(f"[bold red]Symbol '{symbol}' not found in codebase.[/bold red]")
        raise typer.Exit(code=1)

    # Score color
    score_color = "green" if report.score < 30 else ("yellow" if report.score < 70 else "red")

    summary_panel = Panel(
        f"[bold]Target Symbol:[/bold] [cyan]{report.target_name}[/cyan]\n"
        f"[bold]File Location:[/bold] {report.target_file}\n"
        f"[bold]Blast Radius Score:[/bold] [{score_color}]{report.score}/100[/{score_color}]\n"
        f"[bold]Affected Files:[/bold] {len(report.affected_files)}\n"
        f"[bold]Affected Entrypoints (APIs/CLI):[/bold] {len(report.affected_entrypoints)}\n"
        f"[bold]Affected Test Suites:[/bold] {len(report.affected_tests)}",
        title=f"Blast Radius Impact Report: {symbol}",
        border_style=score_color,
    )
    console.print(summary_panel)

    # Upstream tree
    if report.upstream_callers:
        up_tree = Tree(
            f"[bold red][^] UPSTREAM CALLERS ({len(report.upstream_callers)})[/bold red] - Who breaks if this changes:"
        )
        for node in report.upstream_callers:
            badge = f"[{node.category.value}]"
            color = (
                "red"
                if node.category.value == "CRITICAL"
                else ("blue" if node.category.value == "TEST" else "yellow")
            )
            up_tree.add(
                f"[{color}]{badge}[/{color}] [bold]{node.name}[/bold] ({node.file_path}) [dim]depth: {node.depth}[/dim]"
            )
        console.print(up_tree)
    else:
        console.print("[dim]No upstream callers detected (entrypoint or uncalled).[/dim]")

    # Downstream tree
    if report.downstream_callees:
        down_tree = Tree(
            f"[bold green][v] DOWNSTREAM CALLEES ({len(report.downstream_callees)})[/bold green] - Cascaded dependencies triggered:"
        )
        for node in report.downstream_callees:
            down_tree.add(
                f"[bold]{node.name}[/bold] ({node.file_path}) [dim]depth: {node.depth}[/dim]"
            )
        console.print(down_tree)


@app.command()
def cycles(
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Repository path"),
):
    """Detect circular dependencies and import loops using Tarjan's SCC."""
    graph, _ = _build_graph_for_dir(directory)
    detector = CycleDetector(graph)
    report = detector.detect_module_cycles()

    if not report.cycles:
        console.print("[bold green]No circular import dependencies detected.[/bold green]")
        return

    console.print(f"[bold red]Found {report.total_cycles} circular dependency loops:[/bold red]\n")
    for idx, cycle in enumerate(report.cycles, start=1):
        chain = " -> ".join(f"[yellow]{node}[/yellow]" for node in cycle.nodes)
        console.print(f"[bold red]Cycle #{idx}:[/bold red] {chain}")


@app.command()
def dead_code(
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Repository path"),
    include_exported: bool = typer.Option(
        False, "--include-exported", help="Include symbols marked as exported"
    ),
):
    """Detect unreferenced and unreachable symbols (in-degree == 0)."""
    graph, _ = _build_graph_for_dir(directory)
    hunter = DeadCodeHunter(graph)
    report = hunter.find_dead_code(include_exported=include_exported)

    if not report.dead_symbols:
        console.print("[bold green]No dead or unreferenced code detected.[/bold green]")
        return

    table = Table(
        title=f"Dead Code Candidates ({report.total_dead} symbols)", header_style="bold yellow"
    )
    table.add_column("Symbol", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("Location", style="green")
    table.add_column("Complexity", style="dim")

    for s in report.dead_symbols[:50]:
        table.add_row(s.qualified_name, s.kind.value, s.location_str, str(s.complexity))

    console.print(table)
    if report.total_dead > 50:
        console.print(f"[dim]... and {report.total_dead - 50} more symbols omitted.[/dim]")


@app.command()
def metrics(
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Repository path"),
):
    """Show architectural coupling (Ca, Ce, Instability) and hotspot bottlenecks."""
    graph, _ = _build_graph_for_dir(directory)
    analyzer = CouplingAnalyzer(graph)
    data = analyzer.compute_metrics()

    console.print(
        Panel(
            f"[bold]Total Files:[/bold] {data.total_files} | [bold]Symbols:[/bold] {data.total_symbols} | [bold]Edges:[/bold] {data.total_edges}\n"
            f"[bold]Average Cyclomatic Complexity:[/bold] {data.avg_complexity}",
            title="Codebase Architectural Metrics",
        )
    )

    # Coupling table
    table = Table(title="Module Coupling & Instability Metrics", header_style="bold cyan")
    table.add_column("Module", style="green")
    table.add_column("Ca (Afferent)", justify="right")
    table.add_column("Ce (Efferent)", justify="right")
    table.add_column("Instability (I)", justify="right", style="bold")

    for m in data.modules_coupling[:15]:
        inst_color = (
            "green" if m.instability < 0.3 else ("yellow" if m.instability < 0.7 else "red")
        )
        table.add_row(
            m.module_name,
            str(m.afferent_coupling),
            str(m.efferent_coupling),
            f"[{inst_color}]{m.instability:.2f}[/{inst_color}]",
        )

    console.print(table)

    if data.top_bottlenecks:
        b_table = Table(
            title="Top High-Impact Bottleneck Symbols (Most Depended On)", header_style="bold red"
        )
        b_table.add_column("Symbol", style="cyan")
        b_table.add_column("Incoming Dependencies", justify="right", style="bold red")
        for sym_name, count in data.top_bottlenecks[:10]:
            b_table.add_row(sym_name, str(count))
        console.print(b_table)


@app.command()
def export(
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Repository path"),
    format: str = typer.Option(
        "mermaid", "--format", "-f", help="Export format: 'json', 'dot', or 'mermaid'"
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Target output file path"),
):
    """Export the codebase graph to JSON, Graphviz DOT, or Mermaid diagram."""
    graph, _ = _build_graph_for_dir(directory)
    exporter = GraphExporter(graph)

    fmt = format.lower()
    if fmt == "json":
        res = exporter.to_json()
    elif fmt == "dot":
        res = exporter.to_dot()
    elif fmt == "mermaid":
        res = exporter.to_mermaid()
    else:
        console.print(
            f"[bold red]Unsupported format: {format}. Choose 'json', 'dot', or 'mermaid'.[/bold red]"
        )
        raise typer.Exit(code=1)

    if output:
        output.write_text(res, encoding="utf-8")
        console.print(f"[bold green]Graph exported successfully to {output}[/bold green]")
    else:
        print(res)


@app.command()
def serve(
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Repository path"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host address"),
    port: int = typer.Option(8765, "--port", help="Port number"),
):
    """Start local FastAPI interactive graph visualizer."""
    from repograph.web.server import run_server

    console.print(f"[bold green]Starting RepoGraph Visualizer at http://{host}:{port}[/bold green]")
    run_server(directory.resolve(), host=host, port=port)


@app.command()
def tui(
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Repository path"),
):
    """Launch interactive terminal UI (Textual)."""
    from repograph.tui.app import RepoGraphTUI

    app = RepoGraphTUI(target_dir=directory.resolve())
    app.run()


def main():
    app()


if __name__ == "__main__":
    main()
