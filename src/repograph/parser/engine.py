"""Scanner engine orchestrating file discovery and multi-language AST parsing."""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from repograph.config import ScanConfig
from repograph.models import ParsedFile
from repograph.parser.base import ParserRegistry
from repograph.parser.java_parser import JavaParser
from repograph.parser.python_parser import PythonParser
from repograph.parser.ts_parser import TypeScriptParser

logger = logging.getLogger(__name__)


def create_default_registry() -> ParserRegistry:
    """Create and populate registry with standard language parsers."""
    registry = ParserRegistry()
    registry.register(PythonParser())
    registry.register(TypeScriptParser(is_typescript=True))
    registry.register(TypeScriptParser(is_typescript=False))
    registry.register(JavaParser())
    return registry


class ScannerEngine:
    """Discovers source files across a directory and parses them into AST-derived data."""

    def __init__(self, registry: ParserRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def scan_file(self, full_path: Path, root_dir: Path, config: ScanConfig) -> ParsedFile | None:
        """Parse a single file if supported and within size limits."""
        try:
            rel_path = full_path.relative_to(root_dir).as_posix()
        except ValueError:
            rel_path = full_path.as_posix()

        lang = config.get_language(full_path)
        if not lang:
            return None

        parser = self.registry.get(lang)
        if not parser:
            return None

        try:
            if full_path.stat().st_size > config.max_file_size_bytes:
                logger.warning("Skipping file %s exceeding size limit", rel_path)
                return None

            content = full_path.read_bytes()
            return parser.parse(rel_path, content)
        except Exception as e:
            logger.warning("Error parsing %s with %s parser: %s", rel_path, lang, e)
            return None

    def discover_files(self, root_dir: Path, config: ScanConfig) -> list[Path]:
        """Walk directory tree and return paths of supported source files."""
        discovered: list[Path] = []
        root_dir = root_dir.resolve()

        if not root_dir.exists():
            return discovered

        if root_dir.is_file():
            if config.get_language(root_dir):
                return [root_dir]
            return []

        for p in root_dir.rglob("*"):
            if not p.is_file():
                continue

            # Check if any parent component is in ignored_dirs
            rel_parts = p.relative_to(root_dir).parts
            if any(
                part in config.ignored_dirs or (part.startswith(".") and part != ".")
                for part in rel_parts[:-1]
            ):
                continue

            if p.name in config.ignored_files:
                continue

            if config.get_language(p):
                discovered.append(p)

        return discovered

    def scan_directory(
        self,
        config: ScanConfig,
        existing_hashes: dict[str, str] | None = None,
        max_workers: int = 4,
    ) -> dict[str, ParsedFile]:
        """Scan all matching files in root_dir using a thread pool."""
        files = self.discover_files(config.root_dir, config)
        parsed_files: dict[str, ParsedFile] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.scan_file, f, config.root_dir, config): f for f in files
            }
            for future in futures:
                result = future.result()
                if result:
                    parsed_files[result.file_path] = result

        return parsed_files
