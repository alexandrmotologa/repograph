"""Tree-sitter AST parser for Python source files."""

import tree_sitter
import tree_sitter_python
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

PYTHON_BRANCH_NODES = {
    "if_statement",
    "elif_clause",
    "for_statement",
    "while_statement",
    "except_clause",
    "boolean_operator",
    "conditional_expression",
}


class PythonParser(BaseParser):
    """Parses Python source code into symbols, imports, call sites, and inheritance."""

    language_name = "python"

    def __init__(self) -> None:
        self.language = tree_sitter.Language(tree_sitter_python.language())
        self.parser = tree_sitter.Parser(self.language)

    def parse(self, file_path: str, content: bytes) -> ParsedFile:
        tree = self.parser.parse(content)
        root = tree.root_node

        symbols: list[SymbolNode] = []
        imports: list[ImportItem] = []
        calls: list[CallSite] = []
        inheritance: list[InheritanceRelation] = []

        # Track file-level module symbol
        module_id = f"{file_path}::<module>"
        symbols.append(
            SymbolNode(
                id=module_id,
                name=file_path.split("/")[-1].replace(".py", ""),
                qualified_name="<module>",
                kind=SymbolKind.MODULE,
                file_path=file_path,
                line_start=1,
                line_end=root.end_point.row + 1,
            )
        )

        def get_text(node: Node) -> str:
            return self.get_node_text(node, content)

        def extract_decorators(node: Node) -> list[str]:
            decs = []
            if node.parent and node.parent.type == "decorated_definition":
                for child in node.parent.children:
                    if child.type == "decorator":
                        decs.append(get_text(child).strip())
            return decs

        def is_endpoint_decorator(decorators: list[str]) -> bool:
            keywords = [
                "route",
                "get",
                "post",
                "put",
                "delete",
                "patch",
                "api",
                "endpoint",
                "command",
            ]
            for dec in decorators:
                low = dec.lower()
                if any(kw in low for kw in keywords):
                    return True
            return False

        def extract_docstring(body_node: Node | None) -> str | None:
            if not body_node:
                return None
            for child in body_node.children:
                if child.type == "expression_statement":
                    first = child.children[0] if child.children else None
                    if first and first.type == "string":
                        raw = get_text(first).strip()
                        if raw.startswith(('"""', "'''")):
                            return raw[3:-3].strip()
                        elif raw.startswith(('"', "'")):
                            return raw[1:-1].strip()
                        return raw
                elif child.type not in ("comment", "\n"):
                    break
            return None

        def extract_params_and_types(params_node: Node | None) -> tuple[list[str], dict[str, str]]:
            if not params_node:
                return [], {}
            params = []
            param_types = {}
            for child in params_node.children:
                if child.type in ("identifier", "typed_parameter", "default_parameter"):
                    p_name = ""
                    p_type = ""
                    if child.type == "typed_parameter":
                        n_node = child.child_by_field_name("name") or child.children[0]
                        t_node = child.child_by_field_name("type")
                        if n_node:
                            p_name = get_text(n_node)
                        if t_node:
                            p_type = get_text(t_node)
                    elif child.type == "default_parameter":
                        n_node = child.child_by_field_name("name")
                        if n_node:
                            p_name = get_text(n_node)
                    elif child.type == "identifier":
                        p_name = get_text(child)

                    if p_name and p_name not in ("self", "cls"):
                        params.append(p_name)
                        if p_type:
                            param_types[p_name] = p_type
            return params, param_types

        def walk_calls(scope_node: Node, caller_id: str) -> None:
            """Walk inside a function/method body to collect calls."""

            def _visit_call(cur: Node) -> None:
                # Stop if entering a nested function or class; they will have their own scope
                if cur.type in ("function_definition", "class_definition") and cur != scope_node:
                    return

                if cur.type == "call":
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
                    _visit_call(c)

            body = scope_node.child_by_field_name("body")
            if body:
                _visit_call(body)

        def walk_ast(node: Node, scope_prefix: str, parent_id: str) -> None:
            for child in node.children:
                actual_node = child
                if child.type == "decorated_definition":
                    for sub in child.children:
                        if sub.type in ("function_definition", "class_definition"):
                            actual_node = sub
                            break

                if actual_node.type == "function_definition":
                    name_node = actual_node.child_by_field_name("name")
                    if name_node:
                        fn_name = get_text(name_node)
                        qualname = f"{scope_prefix}.{fn_name}" if scope_prefix else fn_name
                        sym_id = f"{file_path}::{qualname}"
                        kind = SymbolKind.METHOD if scope_prefix else SymbolKind.FUNCTION

                        decs = extract_decorators(actual_node)
                        is_entry = (
                            is_endpoint_decorator(decs)
                            or fn_name == "main"
                            or fn_name.startswith("test_")
                        )
                        doc = extract_docstring(actual_node.child_by_field_name("body"))
                        params, p_types = extract_params_and_types(
                            actual_node.child_by_field_name("parameters")
                        )
                        complexity = estimate_cyclomatic_complexity(
                            actual_node, PYTHON_BRANCH_NODES
                        )

                        symbols.append(
                            SymbolNode(
                                id=sym_id,
                                name=fn_name,
                                qualified_name=qualname,
                                kind=kind,
                                file_path=file_path,
                                line_start=actual_node.start_point.row + 1,
                                line_end=actual_node.end_point.row + 1,
                                docstring=doc,
                                parameters=params,
                                param_types=p_types,
                                is_exported=not fn_name.startswith("_"),
                                is_entrypoint=is_entry,
                                complexity=complexity,
                            )
                        )

                        walk_calls(actual_node, sym_id)

                        # Recursively check for nested functions
                        body = actual_node.child_by_field_name("body")
                        if body:
                            walk_ast(body, qualname, sym_id)

                elif actual_node.type == "class_definition":
                    name_node = actual_node.child_by_field_name("name")
                    if name_node:
                        class_name = get_text(name_node)
                        qualname = f"{scope_prefix}.{class_name}" if scope_prefix else class_name
                        class_id = f"{file_path}::{qualname}"

                        doc = extract_docstring(actual_node.child_by_field_name("body"))
                        symbols.append(
                            SymbolNode(
                                id=class_id,
                                name=class_name,
                                qualified_name=qualname,
                                kind=SymbolKind.CLASS,
                                file_path=file_path,
                                line_start=actual_node.start_point.row + 1,
                                line_end=actual_node.end_point.row + 1,
                                docstring=doc,
                                is_exported=not class_name.startswith("_"),
                                is_entrypoint=class_name.endswith("Test")
                                or class_name.startswith("Test"),
                                complexity=1,
                            )
                        )

                        # Superclasses
                        arg_list = actual_node.child_by_field_name("superclasses")
                        if arg_list:
                            for arg in arg_list.children:
                                if arg.type in ("identifier", "attribute"):
                                    parent_name = get_text(arg)
                                    inheritance.append(
                                        InheritanceRelation(
                                            child_id=class_id,
                                            parent_name=parent_name,
                                            relation=EdgeType.EXTENDS,
                                        )
                                    )

                        body = actual_node.child_by_field_name("body")
                        if body:
                            walk_ast(body, qualname, class_id)

                elif actual_node.type == "import_statement":
                    # import a, b as c
                    for c in actual_node.children:
                        if c.type == "dotted_name":
                            mod_name = get_text(c)
                            imports.append(
                                ImportItem(
                                    source_module=mod_name,
                                    imported_name=mod_name.split(".")[-1],
                                    line_number=actual_node.start_point.row + 1,
                                )
                            )
                        elif c.type == "aliased_import":
                            name_sub = c.child_by_field_name("name")
                            alias_sub = c.child_by_field_name("alias")
                            if name_sub:
                                mod_name = get_text(name_sub)
                                alias_name = get_text(alias_sub) if alias_sub else None
                                imports.append(
                                    ImportItem(
                                        source_module=mod_name,
                                        imported_name=mod_name.split(".")[-1],
                                        alias=alias_name,
                                        line_number=actual_node.start_point.row + 1,
                                    )
                                )

                elif actual_node.type == "import_from_statement":
                    # from module import a, b as c
                    mod_node = actual_node.child_by_field_name("module_name")
                    mod_name = get_text(mod_node) if mod_node else ""
                    # Handle relative imports (e.g. from .service import ...)
                    if not mod_name:
                        for c in actual_node.children:
                            if c.type == "relative_import":
                                mod_name = get_text(c)
                                break

                    for c in actual_node.children:
                        if c.type == "dotted_name" and c != mod_node:
                            imp_name = get_text(c)
                            imports.append(
                                ImportItem(
                                    source_module=mod_name,
                                    imported_name=imp_name,
                                    line_number=actual_node.start_point.row + 1,
                                )
                            )
                        elif c.type == "aliased_import":
                            name_sub = c.child_by_field_name("name")
                            alias_sub = c.child_by_field_name("alias")
                            if name_sub:
                                imp_name = get_text(name_sub)
                                alias_name = get_text(alias_sub) if alias_sub else None
                                imports.append(
                                    ImportItem(
                                        source_module=mod_name,
                                        imported_name=imp_name,
                                        alias=alias_name,
                                        line_number=actual_node.start_point.row + 1,
                                    )
                                )
                        elif c.type == "wildcard_import":
                            imports.append(
                                ImportItem(
                                    source_module=mod_name,
                                    imported_name="*",
                                    is_wildcard=True,
                                    line_number=actual_node.start_point.row + 1,
                                )
                            )

                elif actual_node.type not in (
                    "function_definition",
                    "class_definition",
                    "decorated_definition",
                ):
                    # Check top-level statements for top-level calls
                    if actual_node.type == "expression_statement":
                        first = actual_node.children[0] if actual_node.children else None
                        if first and first.type == "call":
                            func_node = first.child_by_field_name("function")
                            if func_node:
                                calls.append(
                                    CallSite(
                                        caller_id=module_id,
                                        callee_name=get_text(func_node),
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
