"""Tree-sitter AST parser for Rust source files."""

import tree_sitter
import tree_sitter_rust
from tree_sitter import Node

from repograph.models import (
    CallSite,
    EdgeType,
    ImportItem,
    InheritanceRelation,
    ParsedFile,
    SymbolKind,
    SymbolNode,
)
from repograph.parser.base import (
    BaseParser,
    compute_content_hash,
    estimate_cyclomatic_complexity,
)

RUST_BRANCH_NODES = {
    "if_expression",
    "for_expression",
    "while_expression",
    "loop_expression",
    "match_arm",
    "try_expression",
}


class RustParser(BaseParser):
    """Parses Rust source code into crates, structs, enums, traits, impl methods, and calls."""

    language_name = "rust"

    def __init__(self) -> None:
        self.language = tree_sitter.Language(tree_sitter_rust.language())
        self.parser = tree_sitter.Parser(self.language)

    def parse(self, file_path: str, content: bytes) -> ParsedFile:
        tree = self.parser.parse(content)
        root = tree.root_node

        symbols: list[SymbolNode] = []
        imports: list[ImportItem] = []
        calls: list[CallSite] = []
        inheritance: list[InheritanceRelation] = []

        def get_text(node: Node) -> str:
            return self.get_node_text(node, content)

        module_id = f"{file_path}::<module>"
        file_stem = file_path.split("/")[-1].replace(".rs", "")
        symbols.append(
            SymbolNode(
                id=module_id,
                name=file_stem,
                qualified_name="<module>",
                kind=SymbolKind.MODULE,
                file_path=file_path,
                line_start=1,
                line_end=root.end_point.row + 1,
            )
        )

        def extract_params_and_types(params_node: Node | None) -> tuple[list[str], dict[str, str]]:
            if not params_node:
                return [], {}
            params: list[str] = []
            param_types: dict[str, str] = {}

            for child in params_node.children:
                if child.type == "parameter":
                    p_name = ""
                    p_type = ""
                    pattern_node = child.child_by_field_name("pattern")
                    type_node = child.child_by_field_name("type")

                    if pattern_node:
                        p_name = get_text(pattern_node)
                    if type_node:
                        p_type = get_text(type_node).lstrip("&").strip()

                    if p_name and p_name not in ("self", "&self", "&mut self"):
                        params.append(p_name)
                        if p_type:
                            param_types[p_name] = p_type

            return params, param_types

        def walk_calls(scope_node: Node, caller_id: str) -> None:
            def _visit(cur: Node) -> None:
                if cur.type == "function_item" and cur != scope_node:
                    return

                if cur.type == "call_expression":
                    func_node = cur.child_by_field_name("function")
                    if func_node:
                        callee_expr = get_text(func_node)
                        calls.append(
                            CallSite(
                                caller_id=caller_id,
                                callee_name=callee_expr,
                                line_number=cur.start_point.row + 1,
                                file_path=file_path,
                            )
                        )

                for c in cur.children:
                    _visit(c)

            body = scope_node.child_by_field_name("body")
            if body:
                _visit(body)

        for child in root.children:
            if child.type == "use_declaration":
                # use crate::path::Symbol;
                full_use = get_text(child).replace("use ", "").rstrip(";").strip()
                last_part = full_use.split("::")[-1].strip()
                imports.append(
                    ImportItem(
                        source_module="::".join(full_use.split("::")[:-1]),
                        imported_name=last_part,
                        line_number=child.start_point.row + 1,
                    )
                )

            elif child.type in ("struct_item", "enum_item"):
                name_node = child.child_by_field_name("name")
                if name_node:
                    s_name = get_text(name_node)
                    s_id = f"{file_path}::{s_name}"
                    is_exported = any(ch.type == "visibility_modifier" for ch in child.children)

                    symbols.append(
                        SymbolNode(
                            id=s_id,
                            name=s_name,
                            qualified_name=s_name,
                            kind=SymbolKind.CLASS,
                            file_path=file_path,
                            line_start=child.start_point.row + 1,
                            line_end=child.end_point.row + 1,
                            is_exported=is_exported,
                            complexity=1,
                        )
                    )

            elif child.type == "trait_item":
                name_node = child.child_by_field_name("name")
                if name_node:
                    t_name = get_text(name_node)
                    t_id = f"{file_path}::{t_name}"
                    is_exported = any(ch.type == "visibility_modifier" for ch in child.children)

                    symbols.append(
                        SymbolNode(
                            id=t_id,
                            name=t_name,
                            qualified_name=t_name,
                            kind=SymbolKind.INTERFACE,
                            file_path=file_path,
                            line_start=child.start_point.row + 1,
                            line_end=child.end_point.row + 1,
                            is_exported=is_exported,
                            complexity=1,
                        )
                    )

            elif child.type == "impl_item":
                # impl OrderService { ... } or impl Payment for OrderService { ... }
                type_node = child.child_by_field_name("type")
                trait_node = child.child_by_field_name("trait")
                target_type = get_text(type_node) if type_node else ""
                trait_name = get_text(trait_node) if trait_node else ""

                if target_type and trait_name:
                    inheritance.append(
                        InheritanceRelation(
                            child_id=f"{file_path}::{target_type}",
                            parent_name=trait_name,
                            relation=EdgeType.IMPLEMENTS,
                        )
                    )

                body = child.child_by_field_name("body")
                if body:
                    for m in body.children:
                        if m.type == "function_item":
                            m_name_node = m.child_by_field_name("name")
                            if m_name_node:
                                m_name = get_text(m_name_node)
                                qualname = f"{target_type}.{m_name}" if target_type else m_name
                                m_id = f"{file_path}::{qualname}"
                                params, param_types = extract_params_and_types(
                                    m.child_by_field_name("parameters")
                                )
                                complexity = estimate_cyclomatic_complexity(m, RUST_BRANCH_NODES)
                                is_exported = any(
                                    ch.type == "visibility_modifier" for ch in m.children
                                )

                                symbols.append(
                                    SymbolNode(
                                        id=m_id,
                                        name=m_name,
                                        qualified_name=qualname,
                                        kind=SymbolKind.METHOD,
                                        file_path=file_path,
                                        line_start=m.start_point.row + 1,
                                        line_end=m.end_point.row + 1,
                                        parameters=params,
                                        param_types=param_types,
                                        is_exported=is_exported,
                                        complexity=complexity,
                                    )
                                )
                                walk_calls(m, m_id)

            elif child.type == "function_item":
                name_node = child.child_by_field_name("name")
                if name_node:
                    fn_name = get_text(name_node)
                    fn_id = f"{file_path}::{fn_name}"
                    params, param_types = extract_params_and_types(
                        child.child_by_field_name("parameters")
                    )
                    complexity = estimate_cyclomatic_complexity(child, RUST_BRANCH_NODES)
                    is_exported = any(ch.type == "visibility_modifier" for ch in child.children)
                    is_entry = fn_name == "main" or fn_name.startswith("test_")

                    symbols.append(
                        SymbolNode(
                            id=fn_id,
                            name=fn_name,
                            qualified_name=fn_name,
                            kind=SymbolKind.FUNCTION,
                            file_path=file_path,
                            line_start=child.start_point.row + 1,
                            line_end=child.end_point.row + 1,
                            parameters=params,
                            param_types=param_types,
                            is_exported=is_exported,
                            is_entrypoint=is_entry,
                            complexity=complexity,
                        )
                    )
                    walk_calls(child, fn_id)

        return ParsedFile(
            file_path=file_path,
            language=self.language_name,
            content_hash=compute_content_hash(content),
            symbols=symbols,
            imports=imports,
            calls=calls,
            inheritance=inheritance,
        )
