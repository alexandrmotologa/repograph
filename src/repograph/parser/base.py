"""Base interface and registry for Tree-sitter language parsers."""

import hashlib
from abc import ABC, abstractmethod

from tree_sitter import Node

from repograph.models import ParsedFile


def compute_content_hash(content: bytes) -> str:
    """Compute SHA256 checksum for source file content."""
    return hashlib.sha256(content).hexdigest()


def estimate_cyclomatic_complexity(node: Node, branch_types: set[str]) -> int:
    """Estimate cyclomatic complexity by counting branching statements in AST."""
    complexity = 1

    def _traverse(cur: Node):
        nonlocal complexity
        if cur.type in branch_types:
            complexity += 1
        for child in cur.children:
            _traverse(child)

    _traverse(node)
    return complexity


class BaseParser(ABC):
    """Abstract base class for all language-specific Tree-sitter parsers."""

    language_name: str

    @abstractmethod
    def parse(self, file_path: str, content: bytes) -> ParsedFile:
        """Parse source content into symbols, imports, calls, and inheritance relations."""
        pass

    @staticmethod
    def get_node_text(node: Node, content: bytes) -> str:
        """Retrieve decoded utf-8 string for a Tree-sitter node."""
        return content[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


class ParserRegistry:
    """Central registry mapping language names to parser instances."""

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}

    def register(self, parser: BaseParser) -> None:
        """Register a language parser instance."""
        self._parsers[parser.language_name.lower()] = parser

    def get(self, language_name: str) -> BaseParser | None:
        """Retrieve parser by language name."""
        return self._parsers.get(language_name.lower())

    def supported_languages(self) -> list[str]:
        """List all supported language keys."""
        return list(self._parsers.keys())
