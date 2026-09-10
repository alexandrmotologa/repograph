"""Terminal User Interface for interactive codebase knowledge graph exploration."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, OptionList
from textual.widgets.option_list import Option

from repograph.analyzer.blast_radius import BlastRadiusCalculator
from repograph.config import ScanConfig
from repograph.graph.builder import GraphBuilder
from repograph.graph.query import GraphQuery
from repograph.models import SymbolKind, SymbolNode
from repograph.parser.engine import ScannerEngine
from repograph.tui.widgets import CallHierarchyTree, SymbolDetailsWidget


class RepoGraphTUI(App):
    """Interactive terminal dashboard for exploring symbols, callers, and blast radius."""

    TITLE = "RepoGraph Terminal Dashboard"
    CSS = """
    Screen {
        background: #121417;
    }

    #left_pane {
        width: 45%;
        border-right: solid #2a313d;
        padding: 1;
    }

    #right_pane {
        width: 55%;
        padding: 1;
    }

    Input {
        margin-bottom: 1;
        border: tall #00bcd4;
    }

    OptionList {
        height: 18;
        border: solid #2a313d;
        background: #181c24;
    }

    CallHierarchyTree {
        height: 1fr;
        border: solid #2a313d;
        background: #181c24;
        margin-top: 1;
    }

    SymbolDetailsWidget {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("/", "focus_search", "Search"),
        ("r", "reload", "Reload"),
    ]

    def __init__(self, target_dir: Path) -> None:
        super().__init__()
        self.target_dir = target_dir
        self.config = ScanConfig(root_dir=target_dir)
        self.engine = ScannerEngine()
        self.builder = GraphBuilder()
        self.graph = None
        self.symbols: list[SymbolNode] = []
        self.filtered_symbols: list[SymbolNode] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left_pane"):
                yield Input(
                    placeholder="Type to filter symbols (e.g. 'cancel')...", id="search_input"
                )
                yield OptionList(id="symbol_list")
                yield CallHierarchyTree("Call Hierarchy", id="call_tree")
            with Vertical(id="right_pane"):
                yield SymbolDetailsWidget(id="symbol_details")
        yield Footer()

    def on_mount(self) -> None:
        self.action_reload()

    def action_focus_search(self) -> None:
        self.query_one("#search_input", Input).focus()

    def action_reload(self) -> None:
        """Scan directory and populate symbols."""
        parsed_files = self.engine.scan_directory(self.config)
        self.graph = self.builder.build(parsed_files)
        self.query = GraphQuery(self.graph)
        self.calc = BlastRadiusCalculator(self.graph)

        self.symbols = [
            sym for sym in self.builder.symbols_by_id.values() if sym.kind != SymbolKind.MODULE
        ]
        self.symbols.sort(key=lambda s: s.qualified_name)
        self.filtered_symbols = self.symbols[:]
        self._update_symbol_list()

    def _update_symbol_list(self) -> None:
        opt_list = self.query_one("#symbol_list", OptionList)
        opt_list.clear_options()
        for sym in self.filtered_symbols[:100]:
            opt_list.add_option(Option(f"{sym.qualified_name} ({sym.kind.value})", id=sym.id))

        if self.filtered_symbols:
            self._select_symbol(self.filtered_symbols[0])

    def on_input_changed(self, event: Input.Changed) -> None:
        q = event.value.lower().strip()
        if not q:
            self.filtered_symbols = self.symbols[:]
        else:
            self.filtered_symbols = [
                s for s in self.symbols if q in s.qualified_name.lower() or q in s.file_path.lower()
            ]
        self._update_symbol_list()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        opt_id = event.option.id
        if opt_id:
            sym = self.builder.symbols_by_id.get(opt_id)
            if sym:
                self._select_symbol(sym)

    def _select_symbol(self, sym: SymbolNode) -> None:
        report = self.calc.calculate(sym.id) if self.calc else None
        details = self.query_one("#symbol_details", SymbolDetailsWidget)
        details.update_symbol(sym, self.target_dir, report)

        tree = self.query_one("#call_tree", CallHierarchyTree)
        if report:
            tree.populate_hierarchy(report)
