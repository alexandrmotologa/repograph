"""Unit tests for Tree-sitter Go and Rust parsers."""

from repograph.models import SymbolKind
from repograph.parser.go_parser import GoParser
from repograph.parser.rust_parser import RustParser


def test_go_parser_symbol_and_call_extraction():
    parser = GoParser()
    code = b"""
package service

import "fmt"

type Order struct {
    ID string
}

func (o *Order) Cancel(reason string) bool {
    if reason == "" {
        return false
    }
    fmt.Println(reason)
    return true
}

func CreateOrder(id string) *Order {
    return &Order{ID: id}
}
"""
    parsed = parser.parse("service/order.go", code)
    assert parsed.language == "go"
    assert len(parsed.imports) >= 1
    assert any(i.source_module == "fmt" for i in parsed.imports)

    syms = {s.name: s for s in parsed.symbols}
    assert "Order" in syms
    assert syms["Order"].kind == SymbolKind.CLASS

    assert "Cancel" in syms
    assert syms["Cancel"].kind == SymbolKind.METHOD
    assert syms["Cancel"].qualified_name == "Order.Cancel"
    assert "reason" in syms["Cancel"].parameters
    assert syms["Cancel"].param_types.get("reason") == "string"

    assert "CreateOrder" in syms
    assert syms["CreateOrder"].kind == SymbolKind.FUNCTION


def test_rust_parser_symbol_and_call_extraction():
    parser = RustParser()
    code = b"""
pub struct Calculator {
    pub precision: u32,
}

pub trait MathOp {
    fn calculate(&self, val: f64) -> f64;
}

impl MathOp for Calculator {
    fn calculate(&self, val: f64) -> f64 {
        if val > 0.0 {
            val * 2.0
        } else {
            0.0
        }
    }
}

pub fn run_app() {
    let calc = Calculator { precision: 2 };
    calc.calculate(10.0);
}
"""
    parsed = parser.parse("src/calc.rs", code)
    assert parsed.language == "rust"

    syms = {s.name: s for s in parsed.symbols}
    assert "Calculator" in syms
    assert syms["Calculator"].kind == SymbolKind.CLASS

    assert "MathOp" in syms
    assert syms["MathOp"].kind == SymbolKind.INTERFACE

    assert "calculate" in syms
    assert syms["calculate"].kind == SymbolKind.METHOD
    assert syms["calculate"].param_types.get("val") == "f64"

    assert "run_app" in syms
    assert syms["run_app"].kind == SymbolKind.FUNCTION
    assert any(c.callee_name == "calc.calculate" for c in parsed.calls)
