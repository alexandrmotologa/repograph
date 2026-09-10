# Adding New Language Parsers

RepoGraph uses a modular parser registry that allows adding support for new programming languages.

## Architecture

All language parsers implement the `BaseParser` interface defined in `src/repograph/parser/base.py`:

```python
class BaseParser(ABC):
    language_name: str

    @abstractmethod
    def parse(self, file_path: str, content: bytes) -> ParsedFile:
        """Parse source content into symbols, imports, calls, and inheritance relations."""
        pass
```

## Step-by-step implementation guide

### 1. Install Tree-sitter grammar package

Find the official Tree-sitter binding for your target language on PyPI (for example, `tree-sitter-go` or `tree-sitter-rust`):

```bash
uv pip install tree-sitter-go
```

Add the package to `pyproject.toml` under `dependencies`.

### 2. Create the parser module

Create `src/repograph/parser/go_parser.py`:

```python
import tree_sitter
import tree_sitter_go
from tree_sitter import Node
from repograph.parser.base import BaseParser, compute_content_hash
from repograph.models import ParsedFile, SymbolNode, SymbolKind


class GoParser(BaseParser):
    language_name = "go"

    def __init__(self) -> None:
        self.language = tree_sitter.Language(tree_sitter_go.language())
        self.parser = tree_sitter.Parser(self.language)

    def parse(self, file_path: str, content: bytes) -> ParsedFile:
        tree = self.parser.parse(content)
        symbols = []
        # Traverse AST and extract function_declaration, method_declaration, type_declaration
        return ParsedFile(
            file_path=file_path,
            language=self.language_name,
            content_hash=compute_content_hash(content),
            symbols=symbols,
        )
```

### 3. Register parser in the engine

Update `src/repograph/parser/engine.py` in `create_default_registry`:

```python
from repograph.parser.go_parser import GoParser


def create_default_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(PythonParser())
    registry.register(TypeScriptParser(is_typescript=True))
    registry.register(TypeScriptParser(is_typescript=False))
    registry.register(JavaParser())
    registry.register(GoParser())
    return registry
```

### 4. Register file extensions

Update `supported_extensions` in `src/repograph/config.py`:

```python
supported_extensions: dict[str, str] = field(
    default_factory=lambda: {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".go": "go",
    }
)
```

### 5. Write unit tests

Create `tests/unit/test_go_parser.py` and provide sample source snippets to verify symbol and call extraction.
