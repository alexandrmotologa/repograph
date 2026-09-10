"""Tree-sitter AST parser for Java source files."""

import tree_sitter
import tree_sitter_java
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

JAVA_BRANCH_NODES = {
    "if_statement",
    "for_statement",
    "enhanced_for_statement",
    "while_statement",
    "do_statement",
    "catch_clause",
    "switch_block_statement_group",
    "ternary_expression",
}


class JavaParser(BaseParser):
    """Parses Java source files into classes, interfaces, methods, imports, and call sites."""

    language_name = "java"

    def __init__(self) -> None:
        self.language = tree_sitter.Language(tree_sitter_java.language())
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
            if child.type == "package_declaration":
                for sub in child.children:
                    if sub.type in ("scoped_identifier", "identifier"):
                        package_name = get_text(sub)
                        break

        module_id = (
            f"{file_path}::<package:{package_name}>" if package_name else f"{file_path}::<module>"
        )
        symbols.append(
            SymbolNode(
                id=module_id,
                name=package_name or file_path.split("/")[-1].replace(".java", ""),
                qualified_name=package_name or "<package>",
                kind=SymbolKind.MODULE,
                file_path=file_path,
                line_start=1,
                line_end=root.end_point.row + 1,
            )
        )

        def extract_modifiers(node: Node) -> tuple[bool, list[str]]:
            """Returns (is_public, annotations_list)."""
            is_pub = False
            annotations = []
            for child in node.children:
                if child.type == "modifiers":
                    for m in child.children:
                        m_txt = get_text(m)
                        if m_txt == "public":
                            is_pub = True
                        elif m.type in ("annotation", "marker_annotation"):
                            annotations.append(m_txt)
            return is_pub, annotations

        def is_api_endpoint(annotations: list[str]) -> bool:
            endpoint_annos = [
                "GetMapping",
                "PostMapping",
                "PutMapping",
                "DeleteMapping",
                "PatchMapping",
                "RequestMapping",
                "RestController",
                "Controller",
                "Test",
            ]
            for a in annotations:
                if any(ea in a for ea in endpoint_annos):
                    return True
            return False

        def extract_params(params_node: Node | None) -> list[str]:
            if not params_node:
                return []
            params = []
            for child in params_node.children:
                if child.type == "formal_parameter":
                    for sub in child.children:
                        if sub.type == "identifier":
                            params.append(get_text(sub))
                            break
            return params

        def walk_calls(scope_node: Node, caller_id: str) -> None:
            def _visit(cur: Node) -> None:
                if (
                    cur.type in ("method_declaration", "constructor_declaration")
                    and cur != scope_node
                ):
                    return

                if cur.type == "method_invocation":
                    name_node = cur.child_by_field_name("name")
                    obj_node = cur.child_by_field_name("object")
                    if name_node:
                        m_name = get_text(name_node)
                        if obj_node:
                            full_call = f"{get_text(obj_node)}.{m_name}"
                        else:
                            full_call = m_name

                        calls.append(
                            CallSite(
                                caller_id=caller_id,
                                callee_name=full_call,
                                line_number=cur.start_point.row + 1,
                                file_path=file_path,
                            )
                        )

                for c in cur.children:
                    _visit(c)

            body = scope_node.child_by_field_name("body")
            if body:
                _visit(body)

        def walk_ast(node: Node, scope_prefix: str, parent_id: str) -> None:
            for child in node.children:
                if child.type == "import_declaration":
                    for sub in child.children:
                        if sub.type in ("scoped_identifier", "identifier"):
                            full_imp = get_text(sub)
                            imports.append(
                                ImportItem(
                                    source_module=".".join(full_imp.split(".")[:-1]),
                                    imported_name=full_imp.split(".")[-1],
                                    line_number=child.start_point.row + 1,
                                )
                            )
                            break
                        elif sub.type == "asterisk":
                            # import package.*
                            prev = child.children[child.children.index(sub) - 2]
                            pkg = get_text(prev)
                            imports.append(
                                ImportItem(
                                    source_module=pkg,
                                    imported_name="*",
                                    is_wildcard=True,
                                    line_number=child.start_point.row + 1,
                                )
                            )

                elif child.type in ("class_declaration", "interface_declaration"):
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        cls_name = get_text(name_node)
                        qualname = f"{scope_prefix}.{cls_name}" if scope_prefix else cls_name
                        cls_id = f"{file_path}::{qualname}"
                        kind = (
                            SymbolKind.INTERFACE
                            if child.type == "interface_declaration"
                            else SymbolKind.CLASS
                        )

                        is_pub, annotations = extract_modifiers(child)
                        symbols.append(
                            SymbolNode(
                                id=cls_id,
                                name=cls_name,
                                qualified_name=qualname,
                                kind=kind,
                                file_path=file_path,
                                line_start=child.start_point.row + 1,
                                line_end=child.end_point.row + 1,
                                is_exported=is_pub,
                                is_entrypoint=is_api_endpoint(annotations) or "Test" in cls_name,
                                complexity=1,
                            )
                        )

                        # Check superclass & super interfaces
                        for sub in child.children:
                            if sub.type == "superclass":
                                for p in sub.children:
                                    if p.type in ("type_identifier", "scoped_type_identifier"):
                                        inheritance.append(
                                            InheritanceRelation(
                                                child_id=cls_id,
                                                parent_name=get_text(p),
                                                relation=EdgeType.EXTENDS,
                                            )
                                        )
                            elif sub.type in ("super_interfaces", "extends_interfaces"):
                                for iface in sub.children:
                                    if iface.type in ("type_list", "interface_type_list"):
                                        for p in iface.children:
                                            if p.type in (
                                                "type_identifier",
                                                "scoped_type_identifier",
                                            ):
                                                inheritance.append(
                                                    InheritanceRelation(
                                                        child_id=cls_id,
                                                        parent_name=get_text(p),
                                                        relation=EdgeType.IMPLEMENTS
                                                        if child.type == "class_declaration"
                                                        else EdgeType.EXTENDS,
                                                    )
                                                )

                        body = child.child_by_field_name("body")
                        if body:
                            walk_ast(body, qualname, cls_id)

                elif child.type in ("method_declaration", "constructor_declaration"):
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        m_name = get_text(name_node)
                        qualname = f"{scope_prefix}.{m_name}" if scope_prefix else m_name
                        m_id = f"{file_path}::{qualname}"

                        is_pub, annotations = extract_modifiers(child)
                        is_entry = is_api_endpoint(annotations) or m_name == "main"
                        params = extract_params(child.child_by_field_name("parameters"))
                        complexity = estimate_cyclomatic_complexity(child, JAVA_BRANCH_NODES)

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
                                is_exported=is_pub,
                                is_entrypoint=is_entry,
                                complexity=complexity,
                            )
                        )
                        walk_calls(child, m_id)

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
