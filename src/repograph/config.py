"""RepoGraph configuration, declarative TOML loader, and architectural rule definitions."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ForbiddenImportRule:
    """Rule forbidding imports between architectural layers/modules."""

    from_pattern: str
    to_pattern: str
    message: str = ""
    severity: str = "error"  # "error" or "warning"


@dataclass
class InstabilityRule:
    """Rule asserting maximum allowed Martin Instability (I = Ce / (Ca + Ce))."""

    module_pattern: str
    max_instability: float = 0.5


@dataclass
class ArchitecturalRules:
    """Architectural constraint rules for codebase linter."""

    forbidden_imports: list[ForbiddenImportRule] = field(default_factory=list)
    instability_rules: list[InstabilityRule] = field(default_factory=list)
    max_complexity: int = 20
    max_risk_gate: float | None = None


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
            ".go": "go",
            ".rs": "rust",
        }
    )
    max_file_size_bytes: int = 2 * 1024 * 1024  # 2 MB limit per file to prevent hangs
    enable_cache: bool = True
    cache_dir: Path = field(default_factory=lambda: Path(".repograph"))
    rules: ArchitecturalRules = field(default_factory=ArchitecturalRules)

    def should_scan_dir(self, dir_name: str) -> bool:
        """Check if directory should be traversed."""
        return dir_name not in self.ignored_dirs and not dir_name.startswith(".")

    def get_language(self, file_path: Path) -> str | None:
        """Return the language identifier based on file extension."""
        return self.supported_extensions.get(file_path.suffix.lower())


def load_config(root_dir: Path) -> ScanConfig:
    """Load configuration from repograph.toml or pyproject.toml in root_dir if present."""
    config = ScanConfig(root_dir=root_dir.resolve())

    toml_path = root_dir / "repograph.toml"
    pyproject_path = root_dir / "pyproject.toml"

    data = None
    if toml_path.exists():
        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            pass
    elif pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                raw = tomllib.load(f)
                data = raw.get("tool", {}).get("repograph")
        except Exception:
            pass

    if not data:
        return config

    # Apply configuration
    if "ignored_dirs" in data and isinstance(data["ignored_dirs"], list):
        config.ignored_dirs.update(data["ignored_dirs"])

    if "ignored_files" in data and isinstance(data["ignored_files"], list):
        config.ignored_files.update(data["ignored_files"])

    if "max_file_size_bytes" in data:
        config.max_file_size_bytes = int(data["max_file_size_bytes"])

    if "enable_cache" in data:
        config.enable_cache = bool(data["enable_cache"])

    rules_data = data.get("rules", {})
    if rules_data:
        forbidden = []
        for r in rules_data.get("forbidden_imports", []):
            if "from" in r and "to" in r:
                forbidden.append(
                    ForbiddenImportRule(
                        from_pattern=r["from"],
                        to_pattern=r["to"],
                        message=r.get("message", ""),
                        severity=r.get("severity", "error"),
                    )
                )
        config.rules.forbidden_imports = forbidden

        inst_rules = []
        for r in rules_data.get("max_instability", []):
            if "module" in r:
                inst_rules.append(
                    InstabilityRule(
                        module_pattern=r["module"],
                        max_instability=float(r.get("max_i", 0.5)),
                    )
                )
        config.rules.instability_rules = inst_rules

        if "max_complexity" in rules_data:
            config.rules.max_complexity = int(rules_data["max_complexity"])

        if "max_risk_gate" in rules_data:
            config.rules.max_risk_gate = float(rules_data["max_risk_gate"])

    return config
