"""Unit tests for Tree-sitter multi-language parsers."""

from repograph.models import SymbolKind
from repograph.parser.java_parser import JavaParser
from repograph.parser.python_parser import PythonParser
from repograph.parser.ts_parser import TypeScriptParser


def test_python_parser_symbol_extraction():
    parser = PythonParser()
    code = b'''
import os
from services.order import cancel_order

class OrderService:
    """Handles orders."""
    def process(self, order_id: str):
        if order_id:
            cancel_order(order_id)
        return True
'''
    parsed = parser.parse("service.py", code)
    assert parsed.language == "python"
    assert len(parsed.imports) == 2
    assert any(i.imported_name == "cancel_order" for i in parsed.imports)

    symbols_by_name = {s.name: s for s in parsed.symbols}
    assert "OrderService" in symbols_by_name
    assert symbols_by_name["OrderService"].kind == SymbolKind.CLASS
    assert "process" in symbols_by_name
    assert symbols_by_name["process"].kind == SymbolKind.METHOD
    assert symbols_by_name["process"].complexity == 2  # 1 + if statement
    assert any(c.callee_name == "cancel_order" for c in parsed.calls)


def test_typescript_parser_symbol_extraction():
    parser = TypeScriptParser(is_typescript=True)
    code = b"""
import { Account } from "./account";

export interface User {
  id: string;
}

export class UserService {
  public getUser(id: string): User {
    const acc = new Account();
    return { id };
  }
}
"""
    parsed = parser.parse("user.ts", code)
    assert parsed.language == "typescript"
    symbols_by_name = {s.name: s for s in parsed.symbols}
    assert "User" in symbols_by_name
    assert symbols_by_name["User"].kind == SymbolKind.INTERFACE
    assert "UserService" in symbols_by_name
    assert symbols_by_name["UserService"].kind == SymbolKind.CLASS
    assert "getUser" in symbols_by_name
    assert symbols_by_name["getUser"].kind == SymbolKind.METHOD


def test_java_parser_symbol_extraction():
    parser = JavaParser()
    code = b"""
package com.test;

import java.util.List;

public class App {
    public void run() {
        System.out.println("Hello");
    }
}
"""
    parsed = parser.parse("App.java", code)
    assert parsed.language == "java"
    assert any(s.name == "App" and s.kind == SymbolKind.CLASS for s in parsed.symbols)
    assert any(s.name == "run" and s.kind == SymbolKind.METHOD for s in parsed.symbols)
    assert any(c.callee_name == "System.out.println" for c in parsed.calls)


def test_python_parser_async_function_extraction():
    parser = PythonParser()
    code = b"""
import asyncio

async def fetch_user(user_id: str):
    await asyncio.sleep(0.01)
    return {"id": user_id}

class AsyncClient:
    async def get_data(self):
        return await fetch_user("123")
"""
    parsed = parser.parse("async_service.py", code)
    symbols_by_name = {s.name: s for s in parsed.symbols}
    assert "fetch_user" in symbols_by_name
    assert symbols_by_name["fetch_user"].kind == SymbolKind.FUNCTION
    assert "AsyncClient" in symbols_by_name
    assert "get_data" in symbols_by_name
    assert symbols_by_name["get_data"].kind == SymbolKind.METHOD
    assert any(c.callee_name == "fetch_user" for c in parsed.calls)


def test_scanner_engine_incremental_cache_reuse(tmp_path):
    from repograph.config import ScanConfig
    from repograph.parser.base import compute_content_hash
    from repograph.parser.engine import ScannerEngine

    file_a = tmp_path / "a.py"
    file_a.write_text("def foo():\n    return 42\n", encoding="utf-8")

    config = ScanConfig(root_dir=tmp_path)
    engine = ScannerEngine()

    parsed_1 = engine.scan_directory(config)
    assert "a.py" in parsed_1
    cached_pf = parsed_1["a.py"]
    hashes = {"a.py": compute_content_hash(file_a.read_bytes())}

    # Second scan with cache
    parsed_2 = engine.scan_directory(config, cached_files=parsed_1, existing_hashes=hashes)
    assert parsed_2["a.py"] is cached_pf  # Exact same cached instance reused!
