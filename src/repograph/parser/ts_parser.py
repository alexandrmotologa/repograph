"""Tree-sitter AST parser for TypeScript and JavaScript source files."""

import tree_sitter
import tree_sitter_javascript
import tree_sitter_typescript
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

JS_BRANCH_NODES = {
    "if_statement",
    "for_statement",
    "for_in_statement",
    "while_statement",
    "do_statement",
    "catch_clause",
    "switch_case",
    "ternary_expression",
}


class TypeScriptParser(BaseParser):
    """Parses TypeScript and JavaScript source files into symbols, imports, calls, and inheritance."""

    def __init__(self, is_typescript: bool = True) -> None:
        self.is_typescript = is_typescript
        self.language_name = "typescript" if is_typescript else "javascript"
        if is_typescript:
            self.language = tree_sitter.Language(tree_sitter_typescript.language_typescript())
        else:
            self.language = tree_sitter.Language(tree_sitter_javascript.language())
        self.parser = tree_sitter.Parser(self.language)

    def parse(self, file_path: str, content: bytes) -> ParsedFile:
        tree = self.parser.parse(content)
        root = tree.root_node

        symbols: list[SymbolNode] = []
        imports: list[ImportItem] = []
        calls: list[CallSite] = []
        inheritance: list[InheritanceRelation] = []

        module_id = f"{file_path}::<module>"
        file_name = file_path.split("/")[-1].split(".")[0]
        symbols.append(
            SymbolNode(
                id=module_id,
                name=file_name,
                qualified_name="<module>",
                kind=SymbolKind.MODULE,
                file_path=file_path,
                line_start=1,
                line_end=root.end_point.row + 1,
            )
        )

        def get_text(node: Node) -> str:
            return self.get_node_text(node, content)

        def extract_params(params_node: Node | None) -> list[str]:
            if not params_node:
                return []
            params = []
            for child in params_node.children:
                if child.type in ("identifier", "required_parameter", "optional_parameter"):
                    # Find identifier
                    if child.type == "identifier":
                        params.append(get_text(child))
                    else:
                        for sub in child.children:
                            if sub.type == "identifier":
                                params.append(get_text(sub))
                                break
            return params

        def walk_calls(scope_node: Node, caller_id: str) -> None:
            def _visit(cur: Node) -> None:
                if (
                    cur.type in ("function_declaration", "method_definition", "arrow_function")
                    and cur != scope_node
                ):
                    return

                if cur.type == "call_expression":
                    func_node = cur.child_by_field_name("function")
                    if func_node:
                        callee_expr = get_text(func_node)
                        # Check if this is a require() call
                        if callee_expr == "require":
                            args = cur.child_by_field_name("arguments")
                            if args and args.children:
                                for a in args.children:
                                    if a.type == "string":
                                        mod = get_text(a).strip("'\"")
                                        imports.append(
                                            ImportItem(
                                                source_module=mod,
                                                imported_name=mod.split("/")[-1],
                                                line_number=cur.start_point.row + 1,
                                            )
                                        )
                        else:
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

        def walk_ast(
            node: Node, scope_prefix: str, parent_id: str, is_exported_context: bool = False
        ) -> None:
            for child in node.children:
                actual_node = child
                is_exported = is_exported_context

                if child.type == "export_statement":
                    is_exported = True
                    for sub in child.children:
                        if sub.type in (
                            "function_declaration",
                            "class_declaration",
                            "interface_declaration",
                            "lexical_declaration",
                            "variable_declaration",
                        ):
                            actual_node = sub
                            break

                if actual_node.type == "function_declaration":
                    name_node = actual_node.child_by_field_name("name")
                    if name_node:
                        fn_name = get_text(name_node)
                        qualname = f"{scope_prefix}.{fn_name}" if scope_prefix else fn_name
                        sym_id = f"{file_path}::{qualname}"
                        is_entry = fn_name in ("main", "handler") or fn_name.startswith("test")
                        params = extract_params(actual_node.child_by_field_name("parameters"))
                        complexity = estimate_cyclomatic_complexity(actual_node, JS_BRANCH_NODES)

                        symbols.append(
                            SymbolNode(
                                id=sym_id,
                                name=fn_name,
                                qualified_name=qualname,
                                kind=SymbolKind.FUNCTION,
                                file_path=file_path,
                                line_start=actual_node.start_point.row + 1,
                                line_end=actual_node.end_point.row + 1,
                                parameters=params,
                                is_exported=is_exported,
                                is_entrypoint=is_entry,
                                complexity=complexity,
                            )
                        )
                        walk_calls(actual_node, sym_id)

                elif actual_node.type in ("lexical_declaration", "variable_declaration"):
                    # const handler = () => ... or const fn = function() ...
                    for decl in actual_node.children:
                        if decl.type == "variable_declarator":
                            name_node = decl.child_by_field_name("name")
                            val_node = decl.child_by_field_name("value")
                            if (
                                name_node
                                and val_node
                                and val_node.type in ("arrow_function", "function_expression")
                            ):
                                fn_name = get_text(name_node)
                                qualname = f"{scope_prefix}.{fn_name}" if scope_prefix else fn_name
                                sym_id = f"{file_path}::{qualname}"
                                params = extract_params(val_node.child_by_field_name("parameters"))
                                complexity = estimate_cyclomatic_complexity(
                                    val_node, JS_BRANCH_NODES
                                )

                                symbols.append(
                                    SymbolNode(
                                        id=sym_id,
                                        name=fn_name,
                                        qualified_name=qualname,
                                        kind=SymbolKind.FUNCTION,
                                        file_path=file_path,
                                        line_start=decl.start_point.row + 1,
                                        line_end=decl.end_point.row + 1,
                                        parameters=params,
                                        is_exported=is_exported,
                                        is_entrypoint=fn_name in ("main", "handler")
                                        or fn_name.startswith("test"),
                                        complexity=complexity,
                                    )
                                )
                                walk_calls(val_node, sym_id)

                elif actual_node.type == "class_declaration":
                    name_node = actual_node.child_by_field_name("name")
                    if name_node:
                        cls_name = get_text(name_node)
                        qualname = f"{scope_prefix}.{cls_name}" if scope_prefix else cls_name
                        cls_id = f"{file_path}::{qualname}"

                        symbols.append(
                            SymbolNode(
                                id=cls_id,
                                name=cls_name,
                                qualified_name=qualname,
                                kind=SymbolKind.CLASS,
                                file_path=file_path,
                                line_start=actual_node.start_point.row + 1,
                                line_end=actual_node.end_point.row + 1,
                                is_exported=is_exported,
                                complexity=1,
                            )
                        )

                        # Heritage: extends / implements
                        for ch in actual_node.children:
                            if ch.type == "class_heritage":
                                for clause in ch.children:
                                    if clause.type == "extends_clause":
                                        for p in clause.children:
                                            if p.type in (
                                                "identifier",
                                                "type_identifier",
                                                "member_expression",
                                            ):
                                                inheritance.append(
                                                    InheritanceRelation(
                                                        child_id=cls_id,
                                                        parent_name=get_text(p),
                                                        relation=EdgeType.EXTENDS,
                                                    )
                                                )
                                    elif clause.type == "implements_clause":
                                        for p in clause.children:
                                            if p.type in ("identifier", "type_identifier"):
                                                inheritance.append(
                                                    InheritanceRelation(
                                                        child_id=cls_id,
                                                        parent_name=get_text(p),
                                                        relation=EdgeType.IMPLEMENTS,
                                                    )
                                                )

                        body = actual_node.child_by_field_name("body")
                        if body:
                            for m in body.children:
                                if m.type == "method_definition":
                                    m_name_node = m.child_by_field_name("name")
                                    if m_name_node:
                                        m_name = get_text(m_name_node)
                                        m_qual = f"{qualname}.{m_name}"
                                        m_id = f"{file_path}::{m_qual}"
                                        m_params = extract_params(
                                            m.child_by_field_name("parameters")
                                        )
                                        m_comp = estimate_cyclomatic_complexity(m, JS_BRANCH_NODES)

                                        symbols.append(
                                            SymbolNode(
                                                id=m_id,
                                                name=m_name,
                                                qualified_name=m_qual,
                                                kind=SymbolKind.METHOD,
                                                file_path=file_path,
                                                line_start=m.start_point.row + 1,
                                                line_end=m.end_point.row + 1,
                                                parameters=m_params,
                                                is_exported=is_exported,
                                                complexity=m_comp,
                                            )
                                        )
                                        walk_calls(m, m_id)

                elif actual_node.type == "interface_declaration":
                    name_node = actual_node.child_by_field_name("name")
                    if name_node:
                        if_name = get_text(name_node)
                        qualname = f"{scope_prefix}.{if_name}" if scope_prefix else if_name
                        if_id = f"{file_path}::{qualname}"

                        symbols.append(
                            SymbolNode(
                                id=if_id,
                                name=if_name,
                                qualified_name=qualname,
                                kind=SymbolKind.INTERFACE,
                                file_path=file_path,
                                line_start=actual_node.start_point.row + 1,
                                line_end=actual_node.end_point.row + 1,
                                is_exported=is_exported,
                                complexity=1,
                            )
                        )

                elif actual_node.type == "import_statement":
                    source_node = actual_node.child_by_field_name("source")
                    src_mod = get_text(source_node).strip("'\"") if source_node else ""

                    for ch in actual_node.children:
                        if ch.type == "import_clause":
                            for item in ch.children:
                                if item.type == "identifier":
                                    # Default import
                                    imp_name = get_text(item)
                                    imports.append(
                                        ImportItem(
                                            source_module=src_mod,
                                            imported_name=imp_name,
                                            line_number=actual_node.start_point.row + 1,
                                        )
                                    )
                                elif item.type == "named_imports":
                                    for spec in item.children:
                                        if spec.type == "import_specifier":
                                            n = spec.child_by_field_name("name")
                                            a = spec.child_by_field_name("alias")
                                            if n:
                                                imports.append(
                                                    ImportItem(
                                                        source_module=src_mod,
                                                        imported_name=get_text(n),
                                                        alias=get_text(a) if a else None,
                                                        line_number=actual_node.start_point.row + 1,
                                                    )
                                                )
                                elif item.type == "namespace_import":
                                    alias = item.children[-1] if item.children else None
                                    alias_str = get_text(alias) if alias else "*"
                                    imports.append(
                                        ImportItem(
                                            source_module=src_mod,
                                            imported_name="*",
                                            alias=alias_str,
                                            is_wildcard=True,
                                            line_number=actual_node.start_point.row + 1,
                                        )
                                    )

                elif actual_node.type == "expression_statement":
                    # Check top-level calls
                    first = actual_node.children[0] if actual_node.children else None
                    if first and first.type == "call_expression":
                        f_node = first.child_by_field_name("function")
                        if f_node:
                            c_name = get_text(f_node)
                            calls.append(
                                CallSite(
                                    caller_id=module_id,
                                    callee_name=c_name,
                                    line_number=actual_node.start_point.row + 1,
                                    file_path=file_path,
                                )
                            )

        walk_ast(root, "", module_id)

        return ParsedFile(
            file_path=file_path,
            language=self.language_name,
            content_hash=compute_content_hash(content),
            symbols=symbols,
            imports=imports,
            calls=calls,
            inheritance=inheritance,
        )
