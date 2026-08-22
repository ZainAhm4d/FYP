"""
Integration tests for the dashboards API: CRUD, ownership isolation, and the
Day-5 view-only public sharing flow (token generation, no-auth public access,
view-count increment, and revocation).
"""
import uuid

API = "/api/v1"

CONFIG = {
    "charts": [
        {"id": "c1", "title": "Revenue by Category", "plotlySpec": {"data": [], "layout": {}},
         "size": "medium"},
    ],
    "layout": "grid",
}


def _make_dashboard(client, headers, name="My Dashboard"):
    r = client.post(f"{API}/dashboards", headers=headers,
                    json={"name": name, "description": "test", "config_json": CONFIG})
    assert r.status_code == 201, r.text
    return r.json()


def _register_login(client):
    em = f"db_{uuid.uuid4().hex[:8]}@example.com"
    client.post(f"{API}/auth/register",
                json={"email": em, "password": "GoodPass1!", "full_name": "DB"})
    tok = client.post(f"{API}/auth/login",
                      data={"username": em, "password": "GoodPass1!"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


# ── CRUD ───────────────────────────────────────────────────────────────────────

def test_create_and_get_dashboard(client, auth):
    d = _make_dashboard(client, auth["headers"])
    assert d["id"]
    r = client.get(f"{API}/dashboards/{d['id']}", headers=auth["headers"])
    assert r.status_code == 200
    assert r.json()["name"] == "My Dashboard"
    assert len(r.json()["config_json"]["charts"]) == 1


def test_list_dashboards_includes_chart_count(client, auth):
    _make_dashboard(client, auth["headers"], name="Listed")
    r = client.get(f"{API}/dashboards", headers=auth["headers"])
    assert r.status_code == 200
    assert any(d["name"] == "Listed" and d["chart_count"] == 1 for d in r.json())


def test_update_dashboard(client, auth):
    d = _make_dashboard(client, auth["headers"])
    r = client.put(f"{API}/dashboards/{d['id']}", headers=auth["headers"],
                   json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


def test_delete_dashboard(client, auth):
    d = _make_dashboard(client, auth["headers"])
    r = client.delete(f"{API}/dashboards/{d['id']}", headers=auth["headers"])
    assert r.status_code == 204
    assert client.get(f"{API}/dashboards/{d['id']}", headers=auth["headers"]).status_code == 404


def test_create_requires_auth(client):
    r = client.post(f"{API}/dashboards",
                    json={"name": "x", "config_json": CONFIG})
    assert r.status_code == 401


def test_empty_name_rejected(client, auth):
    r = client.post(f"{API}/dashboards", headers=auth["headers"],
                    json={"name": "", "config_json": CONFIG})
    assert r.status_code == 422


def test_ownership_isolation(client, auth):
    d = _make_dashboard(client, auth["headers"])
    other = _register_login(client)
    assert client.get(f"{API}/dashboards/{d['id']}", headers=other).status_code == 404
    assert client.put(f"{API}/dashboards/{d['id']}", headers=other,
                      json={"name": "hax"}).status_code == 404
    assert client.delete(f"{API}/dashboards/{d['id']}", headers=other).status_code == 404


# ── Sharing (Day 5) ────────────────────────────────────────────────────────────

def test_share_flow_public_access_and_view_count(client, auth):
    d = _make_dashboard(client, auth["headers"], name="Shared Dash")

    # Enable sharing
    s = client.post(f"{API}/dashboards/{d['id']}/share", headers=auth["headers"])
    assert s.status_code == 200, s.text
    share = s.json()
    assert share["is_public"] is True
    token = share["share_token"]
    assert token
    assert token in share["share_url"]

    # Public access with NO auth header
    p1 = client.get(f"{API}/dashboards/shared/{token}")
    assert p1.status_code == 200, p1.text
    body = p1.json()
    assert body["name"] == "Shared Dash"
    assert "charts" in body["config_json"]

    # View count increments on each public load
    v1 = p1.json()["view_count"]
    p2 = client.get(f"{API}/dashboards/shared/{token}")
    assert p2.json()["view_count"] == v1 + 1


def test_share_idempotent_token(client, auth):
    d = _make_dashboard(client, auth["headers"])
    t1 = client.post(f"{API}/dashboards/{d['id']}/share", headers=auth["headers"]).json()["share_token"]
    t2 = client.post(f"{API}/dashboards/{d['id']}/share", headers=auth["headers"]).json()["share_token"]
    assert t1 == t2  # re-sharing returns the same token, doesn't churn it


def test_revoke_sharing(client, auth):
    d = _make_dashboard(client, auth["headers"])
    token = client.post(f"{API}/dashboards/{d['id']}/share",
                        headers=auth["headers"]).json()["share_token"]
    # Revoke
    r = client.delete(f"{API}/dashboards/{d['id']}/share", headers=auth["headers"])
    assert r.status_code == 204
    # Public link no longer works
    assert client.get(f"{API}/dashboards/shared/{token}").status_code == 404


def test_public_endpoint_unknown_token_404(client):
    assert client.get(f"{API}/dashboards/shared/doesnotexist").status_code == 404


def test_share_requires_auth(client, auth):
    d = _make_dashboard(client, auth["headers"])
    assert client.post(f"{API}/dashboards/{d['id']}/share").status_code == 401


def test_append_chart_to_existing_dashboard(client, auth):
    """The query-page 'Add to Dashboard' picker flow: GET detail → push chart →
    PUT config_json → chart count grows and the chart persists."""
    did = _make_dashboard(client, auth["headers"], "append-target")["id"]
    dash = client.get(f"{API}/dashboards/{did}", headers=auth["headers"]).json()
    cfg = dash["config_json"]
    before = len(cfg.get("charts", []))
    cfg.setdefault("charts", []).append({
        "id": "chart-appended-1",
        "title": "Appended from query page",
        "plotlySpec": {"data": [{"type": "bar", "x": ["A"], "y": [1]}], "layout": {}},
        "dataset": {"id": 1, "name": "x.csv"},
        "size": "medium",
    })
    cfg["chart_count"] = len(cfg["charts"])
    r = client.put(f"{API}/dashboards/{did}", headers=auth["headers"],
                   json={"config_json": cfg})
    assert r.status_code == 200, r.text
    after = client.get(f"{API}/dashboards/{did}", headers=auth["headers"]).json()
    charts = after["config_json"]["charts"]
    assert len(charts) == before + 1
    assert any(c.get("id") == "chart-appended-1" for c in charts)
