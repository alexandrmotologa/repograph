"""Integration tests for FastAPI web endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from repograph.web.server import create_app

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "python_app"


def test_web_endpoints():
    app = create_app(FIXTURE_DIR)
    client = TestClient(app)

    # 1. Test index page
    res = client.get("/")
    assert res.status_code == 200
    assert "RepoGraph" in res.text

    # 2. Test /api/graph
    res = client.get("/api/graph")
    assert res.status_code == 200
    data = res.json()
    assert "elements" in data
    assert data["total_nodes"] > 0

    # 3. Test /api/blast-radius
    res = client.get("/api/blast-radius?symbol=Order.cancel")
    assert res.status_code == 200
    b_data = res.json()
    assert "score" in b_data
    assert "upstream_callers" in b_data

    # 4. Test /api/cycles
    res = client.get("/api/cycles")
    assert res.status_code == 200
    c_data = res.json()
    assert "total_cycles" in c_data

    # 5. Test /api/metrics
    res = client.get("/api/metrics")
    assert res.status_code == 200
    m_data = res.json()
    assert "total_files" in m_data

    # 6. Test /api/dead-code
    res = client.get("/api/dead-code")
    assert res.status_code == 200
    d_data = res.json()
    assert "total_dead" in d_data

    # 7. Test /api/path
    res = client.get("/api/path?source=cancel_endpoint&target=dispatch")
    assert res.status_code == 200
    p_data = res.json()
    assert "steps" in p_data
    assert p_data["total_hops"] >= 1
