"""Interactive REPL shell for fast conversational codebase exploration."""

from pathlib import Path

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
from repograph.graph.paths import PathFinder
from repograph.graph.query import GraphQuery
from repograph.parser.engine import ScannerEngine


class RepoGraphShell:
    """Interactive command-line shell for querying the codebase graph."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.console = Console()
        self.config = ScanConfig(root_dir=self.root_dir)
        self.engine = ScannerEngine()
        self.builder = GraphBuilder()
        self.reload_graph()

    def reload_graph(self) -> None:
        """Scan directory and rebuild graph."""
        self.parsed_files = self.engine.scan_directory(self.config)
        self.graph = self.builder.build(self.parsed_files)
        self.query = GraphQuery(self.graph)
        self.calc = BlastRadiusCalculator(self.graph)
        self.cycle_det = CycleDetector(self.graph)
        self.dead_hunter = DeadCodeHunter(self.graph)
        self.coupling = CouplingAnalyzer(self.graph)
        self.path_finder = PathFinder(self.graph)
        self.exporter = GraphExporter(self.graph)

    def print_help(self) -> None:
        """Show shell commands."""
        table = Table(title="RepoGraph Interactive Shell Commands", header_style="bold cyan")
        table.add_column("Command", style="green")
        table.add_column("Description")

        table.add_row("search <query>", "Search symbols by name, qualified name, or file")
        table.add_row("callers <symbol>", "Show direct and transitive upstream callers")
        table.add_row("callees <symbol>", "Show direct downstream callees and side-effects")
        table.add_row("blast <symbol>", "Calculate full blast radius impact and risk score")
        table.add_row("path <source> <target>", "Trace the shortest call path between two symbols")
        table.add_row("cycles", "Show circular import dependencies")
        table.add_row("dead", "Show unreferenced dead code candidates")
        table.add_row("metrics", "Show coupling, instability, and bottleneck symbols")
        table.add_row("export <mermaid|json|dot> [out]", "Export graph to format or file")
        table.add_row("reload", "Rescan directory and rebuild graph")
        table.add_row("help", "Show this help table")
        table.add_row("exit / quit", "Exit interactive shell")

        self.console.print(table)

    def run(self) -> None:
        """Run interactive loop."""
        self.console.print(
            Panel(
                f"[bold cyan]RepoGraph Shell v{__version__}[/bold cyan]\n"
                f"Repository: [green]{self.root_dir}[/green] | Nodes: {self.graph.number_of_nodes()} | Edges: {self.graph.number_of_edges()}\n"
                "Type [bold yellow]help[/bold yellow] for available commands, [bold yellow]exit[/bold yellow] to quit.",
                title="Interactive Codebase Intelligence",
            )
        )

        while True:
            try:
                line = input("repograph> ").strip()
                if not line:
                    continue

                parts = line.split()
                cmd = parts[0].lower()
                args = parts[1:]

                if cmd in ("exit", "quit", "q"):
                    self.console.print("[dim]Goodbye![/dim]")
                    break

                elif cmd == "help":
                    self.print_help()

                elif cmd == "reload":
                    self.reload_graph()
                    self.console.print(
                        f"[bold green]Graph reloaded: {self.graph.number_of_nodes()} symbols.[/bold green]"
                    )

                elif cmd == "search":
                    if not args:
                        self.console.print("[yellow]Usage: search <query>[/yellow]")
                        continue
                    results = self.query.find_symbols(args[0])
                    table = Table(title=f"Search Results for '{args[0]}'", header_style="bold cyan")
                    table.add_column("Symbol", style="green")
                    table.add_column("Kind", style="magenta")
                    table.add_column("Location")
                    for r in results[:20]:
                        table.add_row(
                            r["qualified_name"],
                            r.get("kind", ""),
                            f"{r.get('file_path')}:{r.get('line_start')}",
                        )
                    self.console.print(table)

                elif cmd in ("callers", "callees", "blast"):
                    if not args:
                        self.console.print(f"[yellow]Usage: {cmd} <symbol>[/yellow]")
                        continue
                    report = self.calc.calculate(args[0])
                    if not report.target_file and report.score == 0.0:
                        self.console.print(f"[red]Symbol '{args[0]}' not found.[/red]")
                        continue

                    if cmd == "callers":
                        tree = Tree(
                            f"[bold red][^] Upstream Callers of {report.target_name}[/bold red]"
                        )
                        for node in report.upstream_callers:
                            tree.add(
                                f"[{node.category.value}] {node.name} ({node.file_path}) depth:{node.depth}"
                            )
                        self.console.print(tree)

                    elif cmd == "callees":
                        tree = Tree(
                            f"[bold green][v] Downstream Callees of {report.target_name}[/bold green]"
                        )
                        for node in report.downstream_callees:
                            tree.add(f"{node.name} ({node.file_path}) depth:{node.depth}")
                        self.console.print(tree)

                    else:  # blast
                        self.console.print(
                            f"[bold]Target:[/bold] {report.target_name} | [bold]Score:[/bold] {report.score}/100 | "
                            f"[bold]Callers:[/bold] {len(report.upstream_callers)} | [bold]Files:[/bold] {len(report.affected_files)}"
                        )

                elif cmd == "path":
                    if len(args) < 2:
                        self.console.print(
                            "[yellow]Usage: path <source_symbol> <target_symbol>[/yellow]"
                        )
                        continue
                    res = self.path_finder.find_shortest_path(args[0], args[1])
                    if not res:
                        self.console.print(
                            f"[yellow]No directed path found from '{args[0]}' to '{args[1]}'.[/yellow]"
                        )
                    else:
                        self.console.print(
                            f"[bold green]Path found ({res.total_hops} hops):[/bold green]"
                        )
                        for step in res.steps:
                            self.console.print(
                                f"  [cyan]{step.from_name}[/cyan] ({step.from_file}) --|{step.edge_type}|--> [magenta]{step.to_name}[/magenta] ({step.to_file})"
                            )

                elif cmd == "cycles":
                    rep = self.cycle_det.detect_module_cycles()
                    if not rep.cycles:
                        self.console.print("[green]No circular dependencies detected.[/green]")
                    else:
                        for c in rep.cycles:
                            self.console.print(" -> ".join(c.nodes))

                elif cmd == "dead":
                    rep = self.dead_hunter.find_dead_code()
                    self.console.print(f"Found {rep.total_dead} unreferenced symbols.")
                    for s in rep.dead_symbols[:15]:
                        self.console.print(f"  {s.qualified_name} ({s.location_str})")

                elif cmd == "metrics":
                    m = self.coupling.compute_metrics()
                    self.console.print(
                        f"Files: {m.total_files} | Symbols: {m.total_symbols} | Edges: {m.total_edges} | Avg Complexity: {m.avg_complexity}"
                    )

                elif cmd == "export":
                    fmt = args[0].lower() if args else "mermaid"
                    out = (
                        self.exporter.to_mermaid()
                        if fmt == "mermaid"
                        else (self.exporter.to_json() if fmt == "json" else self.exporter.to_dot())
                    )
                    if len(args) > 1:
                        Path(args[1]).write_text(out, encoding="utf-8")
                        self.console.print(f"[green]Exported to {args[1]}[/green]")
                    else:
                        self.console.print(out[:500] + ("..." if len(out) > 500 else ""))

                else:
                    self.console.print(
                        f"[red]Unknown command: '{cmd}'. Type 'help' for available commands.[/red]"
                    )

            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
