from app.deps.auth import require_super_admin
from app.services.admin_tool_funds import snapshot


def test_tool_funds_snapshot_has_expected_tools_and_no_secrets():
    data = snapshot()
    assert data["ok"] is True
    assert data["admin_only"] is True
    ids = [row["id"] for row in data["tools"]]
    for needed in ("openai", "anthropic", "gemini", "ideogram", "tavily", "retell", "stripe", "railway"):
        assert needed in ids
    blob = str(data)
    assert "sk-" not in blob
    assert "rk_" not in blob
    for row in data["tools"]:
        assert "billing_url" in row
        assert row["funds"] in {"ok", "low", "missing", "unknown"}


def test_tool_funds_route_is_admin_only():
    from fastapi.testclient import TestClient

    from app.main import app

    http = TestClient(app)
    denied = http.get("/v1/admin/tool-funds")
    assert denied.status_code in {401, 403}
    app.dependency_overrides[require_super_admin] = lambda: "admin-1"
    try:
        ok = http.get("/v1/admin/tool-funds")
        assert ok.status_code == 200
        body = ok.json()
        assert body["admin_only"] is True
        assert any(row["id"] == "openai" for row in body["tools"])
    finally:
        app.dependency_overrides.clear()
