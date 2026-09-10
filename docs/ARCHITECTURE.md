# RepoGraph Architecture and Technical Design

This document details the internal design of RepoGraph, covering Abstract Syntax Tree parsing, cross-file symbol resolution, graph representation, and cache management.

## 1. Pipeline overview

The analysis pipeline processes source trees through four main stages:

```text
Files on Disk
     │
     ▼ (1. File Discovery)
Path filtering (.gitignore, binary files, max size)
     │
     ▼ (2. Tree-sitter AST Extraction)
Multi-Language Parsers (Python, TS/JS, Java) -> ParsedFile models
     │
     ▼ (3. Symbol Linker & Graph Construction)
NetworkX DiGraph (Nodes: Symbols/Files, Edges: CALLS, IMPORTS, EXTENDS)
     │
     ▼ (4. Analyzers & Consumer Interfaces)
Blast Radius Engine, Cycle Detector, Dead Code Hunter, TUI, Web Visualizer
```

## 2. Data model

The graph is backed by a directed graph (`networkx.DiGraph`) where nodes represent symbols and edges represent structural or dynamic relationships.

### Nodes

Each node represents a distinct code symbol identified by a globally unique ID:
`{relative_file_path}::{qualified_name}`

Example node IDs:
- `services/order_service.py::OrderService.cancel_order`
- `models/order.py::Order`
- `controllers/order_controller.py::<module>`

Node attributes stored in the graph:
- `name`: Short symbol name (e.g. `cancel_order`)
- `qualified_name`: Enclosing scope (e.g. `OrderService.cancel_order`)
- `kind`: Member of `SymbolKind` (`function`, `method`, `class`, `interface`, `module`, `variable`)
- `file_path`: Relative file path
- `line_start` and `line_end`: Source boundaries
- `docstring`: Extracted docstring or doc-comment
- `parameters`: Parameter list
- `is_exported`: Boolean flag based on visibility modifiers or exports
- `is_entrypoint`: Boolean flag for HTTP route handlers, CLI commands, or main entrypoints
- `complexity`: Cyclomatic complexity estimate based on AST branching nodes

### Edges

Edges represent directed relationships with an `edge_type` attribute:
- `CONTAINS`: Structural containment (e.g. `module` contains `class`, `class` contains `method`).
- `IMPORTS`: Dependency relationship from an importing module to an imported module or symbol.
- `CALLS`: Invocation from a caller scope to a callee symbol.
- `EXTENDS`: Class inheritance.
- `IMPLEMENTS`: Interface implementation.

## 3. AST parsing with Tree-sitter

RepoGraph uses modern official Tree-sitter grammar packages (`tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`, `tree-sitter-java`).

### Python parser
- Extracts `function_definition`, `class_definition`, `decorated_definition`.
- Identifies decorators matching common web framework routing patterns (`@app.get`, `@router.post`, `@api.route`).
- Extracts calls inside function and method blocks while isolating nested scopes.
- Handles standard imports and relative imports (`from .services import ...`).

### TypeScript / JavaScript parser
- Handles ES Module imports (`import { X } from '...'`) and CommonJS `require()`.
- Extracts both declared functions and arrow functions assigned to variables.
- Extracts interface declarations and class heritage clauses (`extends` and `implements`).

### Java parser
- Extracts package declarations (`package com.example;`) to build namespaced identifiers.
- Captures annotations such as `@GetMapping`, `@PostMapping`, `@RestController`, `@Test`.
- Resolves class inheritance (`extends`) and interface implementations (`implements`).

## 4. Cross-file symbol resolution

The `GraphBuilder` links call sites to concrete symbol definitions using a multi-step resolution strategy:

1. **Local sibling resolution**: If the caller is a method of class `OrderService` and calls `self.validate()`, the engine looks up `OrderService.validate` in the current file.
2. **Local file resolution**: If the call targets a top-level function in the same file, it is resolved directly.
3. **Import table resolution**: When a file contains `from services.order import cancel_order`, any subsequent call to `cancel_order()` is linked directly to the target node in `services/order.py`.
4. **Member call resolution**: For calls of the form `service.cancel_order()`, if `service` is an instance or alias of `OrderService`, the engine links to `OrderService.cancel_order`.
5. **Unique repository match**: If an un-namespaced call matches exactly one function or method across the entire codebase, it is linked as a high-probability resolution.

## 5. Incremental caching

To avoid re-parsing unchanged files in large repositories:

1. Each parsed file stores a SHA256 content checksum.
2. The `.repograph/cache.json` file stores all serialized `ParsedFile` objects and their hashes.
3. During subsequent scans, files with matching file sizes and checksums bypass Tree-sitter parsing and are reloaded directly from cache in milliseconds.
