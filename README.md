# RepoGraph

RepoGraph is a local-first codebase knowledge graph and blast-radius calculation engine. It parses source files into concrete Abstract Syntax Trees using Tree-sitter, constructs a directed code property graph with NetworkX, tracks call hierarchies across files, calculates refactoring blast radius, detects circular dependencies, and spots unreachable dead code.

RepoGraph runs locally on your machine with zero external cloud dependencies. It includes a terminal interface built with Textual and a local force-directed web visualizer served with FastAPI.

## Supported languages

- **Python**: function and class definitions, method calls, decorators, module imports, and relative package references.
- **TypeScript and JavaScript**: ES modules, CommonJS `require`, classes, interfaces, arrow functions, and call sites.
- **Java**: package structures, classes, interfaces, method declarations, constructor invocations, and inheritance hierarchies.

## Features

- **Blast radius engine**: Computes upstream callers (who breaks when a symbol changes) and downstream callees (what side effects trigger). Generates a quantified impact risk score (0 to 100).
- **Tarjan circular dependency detection**: Identifies cyclic import loops at both module and symbol levels.
- **Dead code detection**: Flags functions, methods, and classes that have zero incoming call references or imports across the codebase.
- **Coupling and instability metrics**: Calculates afferent coupling ($C_a$), efferent coupling ($C_e$), and Martin instability ($I$) per module to locate structural hotspots.
- **Terminal TUI**: Interactive keyboard-driven terminal dashboard with fuzzy search, callers tree, and syntax-highlighted symbol preview.
- **Web visualizer**: Local FastAPI server with an interactive Cytoscape canvas graph supporting click-to-isolate blast radius exploration.
- **CI/CD export**: Generates JSON, Graphviz DOT, and Mermaid diagrams for pull request reviews and documentation.

## Installation

### Prerequisites

- Python 3.12 or newer
- [uv](https://github.com/astral-sh/uv) (recommended) or `pip`

### Install from source

```bash
git clone https://github.com/alexandrmotologa/repograph.git
cd repograph
uv venv
uv pip install -e ".[dev]"
```

Or using pip:

```bash
pip install -e .
```

## Quick start

### 1. Scan a codebase

Scan a repository to see file counts, symbol statistics, detected cycles, and unreferenced code:

```bash
repograph scan ./path/to/project
```

Output:

```text
RepoGraph v0.1.0 scanning ./path/to/project...
    Repository Code Graph Summary    
+-----------------------------------+
| Metric                    | Value |
|---------------------------+-------|
| Scanned Source Files      | 42    |
| Extracted Symbol Nodes    | 318   |
| Graph Dependency Edges    | 524   |
| Circular Import Loops     | 0     |
| Unreferenced Dead Symbols | 6     |
+-----------------------------------+
```

### 2. Calculate blast radius

Determine every caller, controller, and test file affected when refactoring or deleting a function or method:

```bash
repograph blast-radius "OrderService.cancel_order" --dir ./path/to/project
```

Output:

```text
+----------------- Blast Radius Impact Report: OrderService.cancel_order ------------------+
| Target Symbol: cancel_order                                                                |
| File Location: services/order_service.py                                                   |
| Blast Radius Score: 71.8/100                                                               |
| Affected Files: 4                                                                          |
| Affected Entrypoints (APIs/CLI): 2                                                         |
| Affected Test Suites: 2                                                                    |
+--------------------------------------------------------------------------------------------+
[^] UPSTREAM CALLERS (4) - Who breaks if this changes:
+-- [CRITICAL] cancel_endpoint (controllers/order_controller.py) depth: 1
+-- [TEST] test_order_cancellation (tests/test_orders.py) depth: 1
[v] DOWNSTREAM CALLEES (2) - Cascaded dependencies triggered:
+-- cancel (models/order.py) depth: 1
`-- dispatch (infra/outbox.py) depth: 1
```

### 3. Detect circular dependencies

Find circular import cycles across packages:

```bash
repograph cycles --dir ./path/to/project
```

### 4. Locate dead code

List unreferenced symbols with zero incoming calls:

```bash
repograph dead-code --dir ./path/to/project
```

### 5. Inspect coupling and architecture hotspots

Evaluate afferent ($C_a$) and efferent ($C_e$) coupling alongside instability ratings:

```bash
repograph metrics --dir ./path/to/project
```

### 6. Export graph for pull requests or documentation

Export as a Mermaid diagram:

```bash
repograph export --dir ./path/to/project --format mermaid -o graph.mmd
```

Or export as JSON / Graphviz DOT:

```bash
repograph export --dir ./path/to/project --format json -o graph.json
repograph export --dir ./path/to/project --format dot -o graph.dot
```

### 7. Run interactive terminal UI

Launch the Textual TUI to browse symbols and call trees directly in your terminal:

```bash
repograph tui --dir ./path/to/project
```

Keybindings:
- `/`: Focus search input
- `r`: Rescan and reload repository
- `q`: Exit

### 8. Run local web visualizer

Launch the FastAPI web server to inspect the graph in your browser:

```bash
repograph serve --dir ./path/to/project --port 8765
```

Open `http://127.0.0.1:8765` in your browser. Click on any node to isolate its blast radius and highlight upstream and downstream paths.

## Architecture

```text
Source Files (Python, TS/JS, Java)
         │
         ▼
Tree-sitter Language Parsers ───► AST Symbol Extraction (Functions, Classes, Calls, Imports)
         │
         ▼
Graph Builder (NetworkX) ────────► Directed Code Property Graph (DiGraph)
         │
         ├───► Blast Radius Engine (Upstream / Downstream Traversal & Risk Scoring)
         ├───► Cycle Detector (Tarjan's Strongly Connected Components)
         ├───► Dead Code Hunter (Zero in-degree analysis)
         └───► Coupling Analyzer (Ca, Ce, Instability metrics)
         │
         ├───► CLI (Typer & Rich)
         ├───► TUI (Textual Terminal Dashboard)
         └───► Web Server (FastAPI + Cytoscape.js Canvas)
```

For more details on parser design and symbol resolution, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Running tests

Run the test suite with coverage:

```bash
uv run pytest -v --cov=repograph --cov-report=term-missing
```

Run linter and formatting checks:

```bash
uv run ruff check .
uv run ruff format --check .
```

## Docker

Run RepoGraph in a container:

```bash
docker build -t repograph .
docker run --rm -v $(pwd):/workspace repograph scan /workspace
```

To run the web visualizer via Docker:

```bash
docker run --rm -p 8765:8765 -v $(pwd):/workspace repograph serve /workspace --host 0.0.0.0
```

## License

MIT License. See [LICENSE](LICENSE) for details.
