"""Knowledge graph builder linking AST symbols, imports, calls, and inheritance."""

import logging
from pathlib import Path

import networkx as nx

from repograph.models import (
    EdgeType,
    ParsedFile,
    SymbolKind,
    SymbolNode,
)

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Constructs a NetworkX DiGraph representing symbols and relationships across a codebase."""

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()
        self.symbols_by_id: dict[str, SymbolNode] = {}
        self.symbols_by_name: dict[str, list[SymbolNode]] = {}
        self.symbols_by_qualname: dict[str, list[SymbolNode]] = {}
        self.symbols_by_file: dict[str, list[SymbolNode]] = {}

    def build(self, parsed_files: dict[str, ParsedFile]) -> nx.DiGraph:
        """Build full directed code property graph from all parsed files."""
        self.graph.clear()
        self.symbols_by_id.clear()
        self.symbols_by_name.clear()
        self.symbols_by_qualname.clear()
        self.symbols_by_file.clear()

        # Step 1: Add all symbol nodes
        for file_path, parsed in parsed_files.items():
            self.symbols_by_file[file_path] = []
            for sym in parsed.symbols:
                self._add_symbol_node(sym)

        # Step 2: Add structural CONTAINS edges
        for file_path, parsed in parsed_files.items():
            module_id = f"{file_path}::<module>"
            # Java may use <package:name>
            matching_mods = [s for s in parsed.symbols if s.kind == SymbolKind.MODULE]
            if matching_mods:
                module_id = matching_mods[0].id

            for sym in parsed.symbols:
                if sym.id == module_id:
                    continue

                if sym.kind == SymbolKind.METHOD:
                    # Belongs to parent class
                    parts = sym.qualified_name.split(".")
                    if len(parts) >= 2:
                        class_qual = ".".join(parts[:-1])
                        parent_class_id = f"{file_path}::{class_qual}"
                        if self.graph.has_node(parent_class_id):
                            self._add_edge(parent_class_id, sym.id, EdgeType.CONTAINS)
                        elif self.graph.has_node(module_id):
                            self._add_edge(module_id, sym.id, EdgeType.CONTAINS)
                else:
                    # Top-level class or function belongs to module
                    if "." not in sym.qualified_name and self.graph.has_node(module_id):
                        self._add_edge(module_id, sym.id, EdgeType.CONTAINS)

        # Step 3: Link Imports & Cross-File Dependencies
        for file_path, parsed in parsed_files.items():
            self._link_imports(file_path, parsed, parsed_files)

        # Step 4: Link Call Sites
        for file_path, parsed in parsed_files.items():
            self._link_calls(file_path, parsed)

        # Step 5: Link Inheritance
        for file_path, parsed in parsed_files.items():
            self._link_inheritance(file_path, parsed)

        return self.graph

    def _add_symbol_node(self, sym: SymbolNode) -> None:
        self.symbols_by_id[sym.id] = sym
        self.symbols_by_name.setdefault(sym.name, []).append(sym)
        self.symbols_by_qualname.setdefault(sym.qualified_name, []).append(sym)
        self.symbols_by_file.setdefault(sym.file_path, []).append(sym)

        self.graph.add_node(
            sym.id,
            name=sym.name,
            qualified_name=sym.qualified_name,
            kind=sym.kind.value,
            file_path=sym.file_path,
            line_start=sym.line_start,
            line_end=sym.line_end,
            docstring=sym.docstring or "",
            parameters=sym.parameters,
            is_exported=sym.is_exported,
            is_entrypoint=sym.is_entrypoint,
            complexity=sym.complexity,
        )

    def _add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        line_number: int | None = None,
        file_path: str | None = None,
    ) -> None:
        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            return

        self.graph.add_edge(
            source_id,
            target_id,
            edge_type=edge_type.value,
            line_number=line_number,
            file_path=file_path,
        )

    def _link_imports(
        self,
        current_file: str,
        parsed: ParsedFile,
        all_parsed: dict[str, ParsedFile],
    ) -> None:
        current_module_id = next(
            (s.id for s in parsed.symbols if s.kind == SymbolKind.MODULE),
            f"{current_file}::<module>",
        )

        for imp in parsed.imports:
            # Try to locate target file
            target_file = self._resolve_import_path(current_file, imp.source_module, all_parsed)
            if target_file and target_file in all_parsed:
                target_parsed = all_parsed[target_file]
                target_module_id = next(
                    (s.id for s in target_parsed.symbols if s.kind == SymbolKind.MODULE),
                    f"{target_file}::<module>",
                )

                # Link module import
                self._add_edge(
                    current_module_id,
                    target_module_id,
                    EdgeType.IMPORTS,
                    line_number=imp.line_number,
                    file_path=current_file,
                )

                # If a specific symbol was imported (e.g. from service import cancel_order)
                if not imp.is_wildcard and imp.imported_name:
                    for sym in target_parsed.symbols:
                        if sym.name == imp.imported_name or sym.qualified_name.endswith(
                            f".{imp.imported_name}"
                        ):
                            self._add_edge(
                                current_module_id,
                                sym.id,
                                EdgeType.IMPORTS,
                                line_number=imp.line_number,
                                file_path=current_file,
                            )

    def _resolve_import_path(
        self,
        current_file: str,
        source_module: str,
        all_parsed: dict[str, ParsedFile],
    ) -> str | None:
        if not source_module:
            return None

        # Convert dotted module to path: 'services.order' -> 'services/order'
        normalized_mod = source_module.replace(".", "/")
        cur_dir = str(Path(current_file).parent).replace("\\", "/")

        candidates = []
        if source_module.startswith("."):
            # Relative import
            dots = len(source_module) - len(source_module.lstrip("."))
            raw_path = source_module.lstrip(".").replace(".", "/")
            p = Path(current_file).parent
            for _ in range(dots - 1):
                p = p.parent
            base_rel = p.as_posix()
            cand = f"{base_rel}/{raw_path}".strip("/")
            candidates.append(cand)
        else:
            # Absolute or project-root import
            candidates.append(normalized_mod)
            if cur_dir and cur_dir != ".":
                candidates.append(f"{cur_dir}/{normalized_mod}")

        # Check against files with extensions
        for cand in candidates:
            for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".java"):
                full = f"{cand}{ext}"
                if full in all_parsed:
                    return full
                # Directory index: e.g. service/index.ts
                idx = f"{cand}/index{ext}"
                if idx in all_parsed:
                    return idx
                # Python package __init__.py
                init_py = f"{cand}/__init__.py"
                if init_py in all_parsed:
                    return init_py

        # Match by suffix (e.g. 'order_service' matching 'src/services/order_service.py')
        mod_tail = normalized_mod.split("/")[-1]
        for f in all_parsed:
            stem = Path(f).stem
            if stem == mod_tail or Path(f).as_posix().endswith(f"{normalized_mod}.py"):
                return f

        return None

    def _link_calls(self, current_file: str, parsed: ParsedFile) -> None:
        file_symbols = self.symbols_by_file.get(current_file, [])

        # Build local symbol lookup
        local_symbols: dict[str, SymbolNode] = {s.name: s for s in file_symbols}
        local_qualnames: dict[str, SymbolNode] = {s.qualified_name: s for s in file_symbols}

        # Build imported symbols lookup
        imported_symbols: dict[str, str] = {}
        for imp in parsed.imports:
            imp_key = imp.alias or imp.imported_name
            # Find candidate in all symbols
            matching = self.symbols_by_name.get(imp.imported_name, [])
            for m in matching:
                if m.file_path != current_file:
                    imported_symbols[imp_key] = m.id
                    break

        for call in parsed.calls:
            target_id = self._resolve_call_target(
                caller_id=call.caller_id,
                callee_name=call.callee_name,
                current_file=current_file,
                local_symbols=local_symbols,
                local_qualnames=local_qualnames,
                imported_symbols=imported_symbols,
            )

            if target_id and target_id != call.caller_id:
                self._add_edge(
                    call.caller_id,
                    target_id,
                    EdgeType.CALLS,
                    line_number=call.line_number,
                    file_path=current_file,
                )

    def _resolve_call_target(
        self,
        caller_id: str,
        callee_name: str,
        current_file: str,
        local_symbols: dict[str, SymbolNode],
        local_qualnames: dict[str, SymbolNode],
        imported_symbols: dict[str, str],
    ) -> str | None:
        # Strip self., this., super.
        clean_name = callee_name
        for prefix in ("self.", "this.", "super.", "cls."):
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix) :]
                break

        # 1. Check if caller belongs to a class and callee is a sibling method in same class
        caller_sym = self.symbols_by_id.get(caller_id)
        if caller_sym and "." in caller_sym.qualified_name:
            class_prefix = ".".join(caller_sym.qualified_name.split(".")[:-1])
            sibling_qualname = f"{class_prefix}.{clean_name}"
            if sibling_qualname in local_qualnames:
                return local_qualnames[sibling_qualname].id

        # 2. Check local symbols in current file
        if clean_name in local_symbols:
            return local_symbols[clean_name].id

        if clean_name in local_qualnames:
            return local_qualnames[clean_name].id

        # 3. Check imported symbols
        if clean_name in imported_symbols:
            return imported_symbols[clean_name]

        # 4. If callee has dot: e.g. service.cancel() or OrderService.cancel()
        if "." in clean_name:
            obj_name, method_name = clean_name.split(".", 1)
            # Check if obj_name was imported (e.g. OrderService)
            if obj_name in imported_symbols:
                target_class_id = imported_symbols[obj_name]
                # Look for method inside that target
                target_sym = self.symbols_by_id.get(target_class_id)
                if target_sym:
                    expected_method_qual = f"{target_sym.qualified_name}.{method_name}"
                    for m in self.symbols_by_qualname.get(expected_method_qual, []):
                        if m.file_path == target_sym.file_path:
                            return m.id

            # Check if method_name matches any method in the codebase where object matches class
            matches = self.symbols_by_name.get(method_name, [])
            for m in matches:
                if m.kind == SymbolKind.METHOD:
                    class_part = m.qualified_name.split(".")[0].lower()
                    if obj_name.lower() in class_part or class_part in obj_name.lower():
                        return m.id

        # 5. Global unique name match across repository
        matches = self.symbols_by_name.get(clean_name, [])
        non_module_matches = [m for m in matches if m.kind != SymbolKind.MODULE]
        if len(non_module_matches) == 1:
            return non_module_matches[0].id

        return None

    def _link_inheritance(self, current_file: str, parsed: ParsedFile) -> None:
        for inh in parsed.inheritance:
            # Find parent class
            clean_parent = inh.parent_name.split(".")[-1]
            candidates = self.symbols_by_name.get(clean_parent, [])
            target = None
            # Prioritize parent in same file
            for c in candidates:
                if c.file_path == current_file and c.kind in (
                    SymbolKind.CLASS,
                    SymbolKind.INTERFACE,
                ):
                    target = c
                    break
            if not target and candidates:
                for c in candidates:
                    if c.kind in (SymbolKind.CLASS, SymbolKind.INTERFACE):
                        target = c
                        break

            if target:
                self._add_edge(inh.child_id, target.id, inh.relation, file_path=current_file)
