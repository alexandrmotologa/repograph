"""Tree-sitter AST parser for Go source files."""

import tree_sitter
import tree_sitter_go
from tree_sitter import Node

from repograph.models import (
    CallSite,
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

GO_BRANCH_NODES = {
    "if_statement",
    "for_statement",
    "expression_switch_statement",
    "type_switch_statement",
    "select_statement",
    "communication_case",
    "expression_case",
}


class GoParser(BaseParser):
    """Parses Go source code into packages, structs, interfaces, functions, methods, and calls."""

    language_name = "go"

    def __init__(self) -> None:
        self.language = tree_sitter.Language(tree_sitter_go.language())
        self.parser = tree_sitter.Parser(self.language)

    def parse(self, file_path: str, content: bytes) -> ParsedFile:
        tree = self.parser.parse(content)
        root = tree.root_node

        symbols: list[SymbolNode] = []
        imports: list[ImportItem] = []
        calls: list[CallSite] = []
        inheritance: list[InheritanceRelation] = []

        package_name = ""

        def get_text(node: Node) -> str:
            return self.get_node_text(node, content)

        # Detect package
        for child in root.children:
            if child.type == "package_clause":
                for sub in child.children:
                    if sub.type == "package_identifier":
                        package_name = get_text(sub)
                        break

        module_id = (
            f"{file_path}::<package:{package_name}>" if package_name else f"{file_path}::<module>"
        )
        symbols.append(
            SymbolNode(
                id=module_id,
                name=package_name or file_path.split("/")[-1].replace(".go", ""),
                qualified_name=package_name or "<package>",
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
                if child.type == "parameter_declaration":
                    p_name = ""
                    p_type = ""
                    for sub in child.children:
                        if sub.type == "identifier":
                            p_name = get_text(sub)
                        elif sub.type in ("type_identifier", "pointer_type", "qualified_type"):
                            p_type = get_text(sub).lstrip("*")

                    if p_name:
                        params.append(p_name)
                        if p_type:
                            param_types[p_name] = p_type

            return params, param_types

        def walk_calls(scope_node: Node, caller_id: str) -> None:
            def _visit(cur: Node) -> None:
                if cur.type in ("function_declaration", "method_declaration") and cur != scope_node:
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
            if child.type == "import_declaration":
                for sub in child.children:
                    if sub.type == "import_spec":
                        path_node = sub.child_by_field_name("path")
                        name_node = sub.child_by_field_name("name")
                        if path_node:
                            mod_path = get_text(path_node).strip('"')
                            alias = get_text(name_node) if name_node else None
                            imports.append(
                                ImportItem(
                                    source_module=mod_path,
                                    imported_name=alias or mod_path.split("/")[-1],
                                    alias=alias,
                                    line_number=sub.start_point.row + 1,
                                )
                            )
                    elif sub.type == "import_spec_list":
                        for spec in sub.children:
                            if spec.type == "import_spec":
                                path_node = spec.child_by_field_name("path")
                                name_node = spec.child_by_field_name("name")
                                if path_node:
                                    mod_path = get_text(path_node).strip('"')
                                    alias = get_text(name_node) if name_node else None
                                    imports.append(
                                        ImportItem(
                                            source_module=mod_path,
                                            imported_name=alias or mod_path.split("/")[-1],
                                            alias=alias,
                                            line_number=spec.start_point.row + 1,
                                        )
                                    )

            elif child.type == "type_declaration":
                for sub in child.children:
                    if sub.type == "type_spec":
                        name_node = sub.child_by_field_name("name")
                        type_node = sub.child_by_field_name("type")
                        if name_node and type_node:
                            t_name = get_text(name_node)
                            t_id = f"{file_path}::{t_name}"
                            kind = (
                                SymbolKind.INTERFACE
                                if type_node.type == "interface_type"
                                else SymbolKind.CLASS
                            )
                            is_exported = t_name[0].isupper()

                            symbols.append(
                                SymbolNode(
                                    id=t_id,
                                    name=t_name,
                                    qualified_name=t_name,
                                    kind=kind,
                                    file_path=file_path,
                                    line_start=sub.start_point.row + 1,
                                    line_end=sub.end_point.row + 1,
                                    is_exported=is_exported,
                                    complexity=1,
                                )
                            )

            elif child.type == "function_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    fn_name = get_text(name_node)
                    fn_id = f"{file_path}::{fn_name}"
                    params, param_types = extract_params_and_types(
                        child.child_by_field_name("parameters")
                    )
                    complexity = estimate_cyclomatic_complexity(child, GO_BRANCH_NODES)
                    is_exported = fn_name[0].isupper()
                    is_entry = fn_name in ("main", "init") or fn_name.startswith("Test")

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

            elif child.type == "method_declaration":
                name_node = child.child_by_field_name("name")
                recv_node = child.child_by_field_name("receiver")
                if name_node and recv_node:
                    m_name = get_text(name_node)

                    # Extract receiver struct type (e.g. '(s *OrderService)' -> 'OrderService')
                    struct_type = ""
                    for sub in recv_node.children:
                        if sub.type == "parameter_declaration":
                            for part in sub.children:
                                if part.type in ("type_identifier", "pointer_type"):
                                    struct_type = get_text(part).lstrip("*").strip("()")

                    qualname = f"{struct_type}.{m_name}" if struct_type else m_name
                    m_id = f"{file_path}::{qualname}"
                    params, param_types = extract_params_and_types(
                        child.child_by_field_name("parameters")
                    )
                    complexity = estimate_cyclomatic_complexity(child, GO_BRANCH_NODES)
                    is_exported = m_name[0].isupper()

                    symbols.append(
                        SymbolNode(
                            id=m_id,
                            name=m_name,
                            qualified_name=qualname,
                            kind=SymbolKind.METHOD,
                            file_path=file_path,
                            line_start=child.start_point.row + 1,
                            line_end=child.end_point.row + 1,
                            parameters=params,
                            param_types=param_types,
                            is_exported=is_exported,
                            complexity=complexity,
                        )
                    )
                    walk_calls(child, m_id)

        return ParsedFile(
            file_path=file_path,
            language=self.language_name,
            content_hash=compute_content_hash(content),
            symbols=symbols,
            imports=imports,
            calls=calls,
            inheritance=inheritance,
        )
