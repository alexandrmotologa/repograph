"""RepoGraph configuration and path filtering."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScanConfig:
    """Configuration for scanning repositories and building code graphs."""

    root_dir: Path = field(default_factory=lambda: Path("."))
    ignored_dirs: set[str] = field(
        default_factory=lambda: {
            ".git",
            ".repograph",
            ".venv",
            "venv",
            "env",
            "node_modules",
            "target",
            "build",
            "dist",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            ".idea",
            ".vscode",
            ".gradle",
            "out",
            "bin",
        }
    )
    ignored_files: set[str] = field(
        default_factory=lambda: {
            ".DS_Store",
            "Thumbs.db",
        }
    )
    supported_extensions: dict[str, str] = field(
        default_factory=lambda: {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
        }
    )
    max_file_size_bytes: int = 2 * 1024 * 1024  # 2 MB limit per file to prevent hangs
    enable_cache: bool = True
    cache_dir: Path = field(default_factory=lambda: Path(".repograph"))

    def should_scan_dir(self, dir_name: str) -> bool:
        """Check if directory should be traversed."""
        return dir_name not in self.ignored_dirs and not dir_name.startswith(".")

    def get_language(self, file_path: Path) -> str | None:
        """Return the language identifier based on file extension."""
        return self.supported_extensions.get(file_path.suffix.lower())
