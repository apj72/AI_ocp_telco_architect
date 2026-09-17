import pytest
from fastapi.testclient import TestClient
from tps.db import Database


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TPS_SECRET", "")
    import tps.app as app_module
    db = Database(tmp_path / "partners.db")
    monkeypatch.setattr(app_module, "db", db)
    monkeypatch.setattr(app_module, "_DEFAULT_OUTPUT", tmp_path / "output")
    (tmp_path / "output").mkdir()
    from tps.app import app
    return TestClient(app, raise_server_exceptions=True)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_architect_provider_catalog(client):
    r = client.get("/api/architect/providers")
    assert r.status_code == 200
    assert {p["id"] for p in r.json()["providers"]} == {"openai", "claude"}


def test_create_partner(client):
    r = client.post("/api/partners", data={"name": "TestCo"})
    assert r.status_code == 201
    assert r.json()["slug"] == "testco"


def test_create_partner_duplicate(client):
    client.post("/api/partners", data={"name": "TestCo"})
    r = client.post("/api/partners", data={"name": "TestCo"})
    assert r.status_code == 409


def test_create_partner_invalid_name(client):
    r = client.post("/api/partners", data={"name": "!!!"})
    assert r.status_code == 400


def test_partner_detail_not_found(client):
    r = client.get("/partner/does-not-exist")
    assert r.status_code == 404


def test_partner_detail_ok(client):
    client.post("/api/partners", data={"name": "TestCo"})
    r = client.get("/partner/testco")
    assert r.status_code == 200
    assert b"TestCo" in r.content


def test_create_release(client):
    p = client.post("/api/partners", data={"name": "TestCo"}).json()
    r = client.post(f"/api/partners/{p['id']}/releases",
                    data={"release_name": "25R3", "ocp_version": "4.17"})
    assert r.status_code == 201
    assert r.json()["release_name"] == "25R3"


def test_delete_release(client):
    p = client.post("/api/partners", data={"name": "TestCo"}).json()
    rel = client.post(f"/api/partners/{p['id']}/releases",
                      data={"release_name": "25R3", "ocp_version": "4.17"}).json()
    r = client.delete(f"/api/releases/{rel['id']}")
    assert r.status_code == 200


def test_create_operator(client):
    p = client.post("/api/partners", data={"name": "TestCo"}).json()
    r = client.post(f"/api/partners/{p['id']}/operators",
                    data={"operator_name": "sriov-network-operator", "channel": "stable-4.17"})
    assert r.status_code == 201
    assert r.json()["operator_name"] == "sriov-network-operator"


def test_operator_version_pins_roundtrip(client):
    p = client.post("/api/partners", data={"name": "TestCo"}).json()
    rel = client.post(f"/api/partners/{p['id']}/releases",
                      data={"release_name": "25R3", "ocp_version": "4.17"}).json()
    op = client.post(f"/api/partners/{p['id']}/operators",
                     data={"operator_name": "sriov-network-operator"}).json()
    # pin
    r = client.post(f"/api/operators/{op['id']}/pins",
                    data={"release_id": rel["id"], "pinned_version": "4.17.0-202501"})
    assert r.status_code == 200
    # get pins
    pins = client.get(f"/api/operators/{op['id']}/pins").json()
    assert len(pins) == 1
    assert pins[0]["pinned_version"] == "4.17.0-202501"
    # delete pin
    r = client.delete(f"/api/operator-pins/{pins[0]['id']}")
    assert r.status_code == 200
    assert client.get(f"/api/operators/{op['id']}/pins").json() == []


def test_create_domain(client):
    p = client.post("/api/partners", data={"name": "TestCo"}).json()
    r = client.post(f"/api/partners/{p['id']}/domains",
                    data={"name": "networking"})
    assert r.status_code == 201
    assert r.json()["name"] == "networking"


def test_add_ticket(client):
    p = client.post("/api/partners", data={"name": "TestCo"}).json()
    r = client.post(f"/api/partners/{p['id']}/tickets",
                    data={"ecops_key": "ECOPS-100", "summary": "Test ticket"})
    assert r.status_code == 201


def test_login_redirect_when_secret_set(tmp_path, monkeypatch):
    monkeypatch.setenv("TPS_SECRET", "hunter2")
    import importlib, tps.app as app_module
    importlib.reload(app_module)
    db = Database(tmp_path / "partners.db")
    monkeypatch.setattr(app_module, "db", db)
    client = TestClient(app_module.app, raise_server_exceptions=True,
                        follow_redirects=False)
    r = client.get("/")
    assert r.status_code in (302, 307)
    assert "/login" in r.headers["location"]


def test_login_sets_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv("TPS_SECRET", "hunter2")
    import importlib, tps.app as app_module
    importlib.reload(app_module)
    db = Database(tmp_path / "partners.db")
    monkeypatch.setattr(app_module, "db", db)
    client = TestClient(app_module.app, raise_server_exceptions=True,
                        follow_redirects=False)
    r = client.post("/login", data={"secret": "hunter2"})
    assert r.status_code == 303
    assert "tps_auth" in r.cookies
