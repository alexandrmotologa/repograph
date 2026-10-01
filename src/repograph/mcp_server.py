"""Model Context Protocol (MCP) stdio JSON-RPC server for AI coding assistants."""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from repograph.analyzer.blast_radius import BlastRadiusCalculator
from repograph.analyzer.coupling import CouplingAnalyzer
from repograph.analyzer.cycles import CycleDetector
from repograph.analyzer.dead_code import DeadCodeHunter
from repograph.analyzer.linter import ArchitecturalLinter
from repograph.config import load_config
from repograph.graph.builder import GraphBuilder
from repograph.graph.paths import PathFinder
from repograph.graph.query import GraphQuery
from repograph.models import SymbolKind
from repograph.parser.engine import ScannerEngine

logger = logging.getLogger(__name__)


class RepoGraphMCPServer:
    """Stdio JSON-RPC MCP server exposing RepoGraph code intelligence tools."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.config = load_config(self.root_dir)
        self.engine = ScannerEngine()
        self.builder = GraphBuilder()
        self.reload_graph()

    def reload_graph(self) -> None:
        """Parse codebase and construct graph."""
        self.parsed_files = self.engine.scan_directory(self.config)
        self.graph = self.builder.build(self.parsed_files)
        self.query = GraphQuery(self.graph)
        self.calc = BlastRadiusCalculator(self.graph)
        self.cycles = CycleDetector(self.graph)
        self.dead_hunter = DeadCodeHunter(self.graph)
        self.coupling = CouplingAnalyzer(self.graph)
        self.path_finder = PathFinder(self.graph)
        self.linter = ArchitecturalLinter(self.graph, self.config.rules)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return MCP tool schemas."""
        return [
            {
                "name": "search_symbols",
                "description": "Search code symbols by name, qualified name, or file path across the repository.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Symbol name or path query (e.g. 'cancel_order', 'OrderService')",
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["function", "method", "class", "interface", "module"],
                            "description": "Optional symbol kind filter",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 20,
                            "description": "Maximum number of results to return",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_blast_radius",
                "description": "Calculate refactoring blast radius, upstream callers, downstream callees, and risk score (0-100) for a symbol.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Symbol name or ID (e.g. 'OrderService.cancel_order')",
                        },
                        "depth": {
                            "type": "integer",
                            "default": 10,
                            "description": "Max traversal depth",
                        },
                    },
                    "required": ["symbol"],
                },
            },
            {
                "name": "get_upstream_callers",
                "description": "Get all callers and entrypoints that depend on or invoke this symbol (who breaks if it changes).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Symbol name or ID"}
                    },
                    "required": ["symbol"],
                },
            },
            {
                "name": "get_downstream_callees",
                "description": "Get all functions, methods, and services invoked downstream by this symbol.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Symbol name or ID"}
                    },
                    "required": ["symbol"],
                },
            },
            {
                "name": "find_call_path",
                "description": "Find the shortest directed call chain between two symbols across modules.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source caller symbol"},
                        "target": {"type": "string", "description": "Target callee symbol"},
                    },
                    "required": ["source", "target"],
                },
            },
            {
                "name": "get_circular_dependencies",
                "description": "Find all circular import loops across packages and files.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_dead_code",
                "description": "Find unreferenced or unreachable functions, classes, and methods (in-degree == 0).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_exported": {
                            "type": "boolean",
                            "default": False,
                            "description": "Whether to include public/exported symbols",
                        }
                    },
                },
            },
            {
                "name": "get_architectural_metrics",
                "description": "Get afferent coupling (Ca), efferent coupling (Ce), instability (I), and top bottleneck symbols.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "lint_architecture",
                "description": "Verify architectural boundary constraints and layer rules defined in repograph.toml.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatch tool execution and return structured result."""
        if name == "search_symbols":
            query = args.get("query", "")
            kind_str = args.get("kind")
            kind_enum = SymbolKind(kind_str) if kind_str else None
            limit = int(args.get("limit", 20))
            results = self.query.find_symbols(query, kind=kind_enum, limit=limit)
            return {"count": len(results), "symbols": results}

        elif name == "get_blast_radius":
            sym = args.get("symbol", "")
            depth = int(args.get("depth", 10))
            report = self.calc.calculate(sym, max_depth=depth)
            return report.model_dump()

        elif name == "get_upstream_callers":
            sym = args.get("symbol", "")
            report = self.calc.calculate(sym)
            return {
                "target": report.target_name,
                "file": report.target_file,
                "score": report.score,
                "callers": [u.model_dump() for u in report.upstream_callers],
            }

        elif name == "get_downstream_callees":
            sym = args.get("symbol", "")
            report = self.calc.calculate(sym)
            return {
                "target": report.target_name,
                "file": report.target_file,
                "callees": [d.model_dump() for d in report.downstream_callees],
            }

        elif name == "find_call_path":
            src = args.get("source", "")
            tgt = args.get("target", "")
            res = self.path_finder.find_shortest_path(src, tgt)
            if not res:
                return {
                    "found": False,
                    "message": f"No directed path found from '{src}' to '{tgt}'",
                }
            return {"found": True, "path": res.model_dump()}

        elif name == "get_circular_dependencies":
            rep = self.cycles.detect_module_cycles()
            return rep.model_dump()

        elif name == "get_dead_code":
            inc_exp = bool(args.get("include_exported", False))
            rep = self.dead_hunter.find_dead_code(include_exported=inc_exp)
            return rep.model_dump()

        elif name == "get_architectural_metrics":
            m = self.coupling.compute_metrics()
            return m.model_dump()

        elif name == "lint_architecture":
            rep = self.linter.lint()
            return rep.model_dump()

        else:
            raise ValueError(f"Unknown tool: '{name}'")

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single JSON-RPC request."""
        method = request.get("method")
        msg_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "repograph-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }

        elif method == "notifications/initialized":
            return None

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.get_tool_definitions()},
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            try:
                res = self.execute_tool(tool_name, tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]},
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32603, "message": str(e)},
                }

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: '{method}'"},
            }

    def run_stdio(self) -> None:
        """Read newline-delimited JSON-RPC from stdin and write responses to stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError:
                err = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()
