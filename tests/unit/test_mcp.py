"""Unit tests for Model Context Protocol (MCP) server."""

from pathlib import Path

from repograph.mcp_server import RepoGraphMCPServer


def test_mcp_server_initialize_and_tools_list():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    server = RepoGraphMCPServer(fixture_dir)

    # Test initialize request
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    init_resp = server.handle_request(init_req)
    assert init_resp["result"]["serverInfo"]["name"] == "repograph-mcp"

    # Test tools/list
    tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    tools_resp = server.handle_request(tools_req)
    tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
    assert "search_symbols" in tool_names
    assert "get_blast_radius" in tool_names
    assert "find_call_path" in tool_names
    assert "get_dead_code" in tool_names
    assert "get_circular_dependencies" in tool_names
    assert "lint_architecture" in tool_names


def test_mcp_server_tool_calls():
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "python_app"
    server = RepoGraphMCPServer(fixture_dir)

    # Call search_symbols
    search_req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "search_symbols", "arguments": {"query": "cancel"}},
    }
    search_resp = server.handle_request(search_req)
    assert search_resp is not None
    assert "result" in search_resp
    assert "content" in search_resp["result"]

    # Call get_blast_radius
    blast_req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "get_blast_radius", "arguments": {"symbol": "Order.cancel"}},
    }
    blast_resp = server.handle_request(blast_req)
    assert "result" in blast_resp
    assert "content" in blast_resp["result"]

    # Call get_dead_code
    dead_req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "get_dead_code", "arguments": {"include_exported": True}},
    }
    dead_resp = server.handle_request(dead_req)
    assert "result" in dead_resp
