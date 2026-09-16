import os
import pytest
from tps.db import Database, _enc, _dec


# -- partners --

def test_create_and_get_partner(db):
    p = db.create_partner("TestCo", "testco")
    assert p["name"] == "TestCo"
    assert p["slug"] == "testco"
    got = db.get_partner_by_slug("testco")
    assert got["id"] == p["id"]


def test_list_partners_empty(db):
    assert db.list_partners() == []


def test_duplicate_slug_raises(db):
    db.create_partner("TestCo", "testco")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        db.create_partner("TestCo 2", "testco")


def test_delete_partner(db):
    p = db.create_partner("TestCo", "testco")
    db.delete_partner(p["id"])
    assert db.get_partner_by_slug("testco") is None


# -- jira config --

def test_set_and_get_jira_config(db, partner):
    cfg = db.set_jira_config(
        partner["id"], "https://jira.example.com", "user@example.com",
        "secret-token", "ECOPS", "25R", jira_mode="api_key",
    )
    assert cfg["jira_url"] == "https://jira.example.com"
    assert cfg["jira_token"] == "secret-token"


def test_jira_config_returns_none_when_not_set(db, partner):
    assert db.get_jira_config(partner["id"]) is None


def test_jira_config_upsert(db, partner):
    db.set_jira_config(partner["id"], "https://a.com", "a@b.com", "tok1", "P", "v")
    db.set_jira_config(partner["id"], "https://b.com", "a@b.com", "tok2", "P", "v")
    cfg = db.get_jira_config(partner["id"])
    assert cfg["jira_url"] == "https://b.com"
    assert cfg["jira_token"] == "tok2"


# -- encryption --

def test_enc_dec_without_key():
    assert _enc("hello") == "hello"
    assert _dec("hello") == "hello"


def test_enc_dec_with_key(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TPS_MASTER_KEY", key)
    enc = _enc("mysecret")
    assert enc != "mysecret"
    assert _dec(enc) == "mysecret"


def test_dec_plaintext_fallback_with_key(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TPS_MASTER_KEY", key)
    # existing plaintext rows should be returned as-is
    assert _dec("plaintext-token") == "plaintext-token"


def test_jira_token_encrypted_at_rest(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TPS_MASTER_KEY", key)
    db = Database(tmp_path / "enc.db")
    p = db.create_partner("TestCo", "testco")
    db.set_jira_config(p["id"], "https://jira.example.com", "u@e.com",
                       "my-secret-token", "P", "v")
    # raw DB value should not be plaintext
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "enc.db"))
    row = conn.execute("SELECT jira_token FROM partner_jira_config").fetchone()
    assert row[0] != "my-secret-token"
    assert "my-secret-token" not in row[0]
    conn.close()
    # but db layer should decrypt it
    cfg = db.get_jira_config(p["id"])
    assert cfg["jira_token"] == "my-secret-token"


# -- releases --

def test_create_and_list_releases(db, partner):
    r = db.create_release(partner["id"], "25R3", ocp_version="4.17")
    assert r["release_name"] == "25R3"
    releases = db.list_releases(partner["id"])
    assert len(releases) == 1
    assert releases[0]["ocp_version"] == "4.17"


def test_delete_release(db, partner, release):
    db.delete_release(release["id"])
    assert db.list_releases(partner["id"]) == []


# -- operators --

def test_create_and_list_operators(db, partner):
    o = db.create_operator(partner["id"], "sriov-network-operator", channel="stable-4.17")
    assert o["operator_name"] == "sriov-network-operator"
    ops = db.list_operators(partner["id"])
    assert len(ops) == 1


def test_operator_version_pins(db, partner, release):
    op = db.create_operator(partner["id"], "sriov-network-operator")
    pin = db.pin_operator_version(release["id"], op["id"], "4.17.0-202501")
    assert pin["pinned_version"] == "4.17.0-202501"
    pins = db.get_operator_pins(op["id"])
    assert len(pins) == 1
    assert pins[0]["release_name"] == "25R3"


def test_operator_pin_upsert(db, partner, release):
    op = db.create_operator(partner["id"], "sriov-network-operator")
    db.pin_operator_version(release["id"], op["id"], "v1")
    db.pin_operator_version(release["id"], op["id"], "v2")
    pins = db.get_operator_pins(op["id"])
    assert len(pins) == 1
    assert pins[0]["pinned_version"] == "v2"


def test_delete_operator_pin(db, partner, release):
    op = db.create_operator(partner["id"], "sriov-network-operator")
    pin = db.pin_operator_version(release["id"], op["id"], "v1")
    db.delete_operator_pin(pin["id"])
    assert db.get_operator_pins(op["id"]) == []


def test_list_release_operators(db, partner, release):
    op = db.create_operator(partner["id"], "sriov-network-operator")
    db.pin_operator_version(release["id"], op["id"], "4.17.0")
    rows = db.list_release_operators(partner["id"])
    assert len(rows) == 1
    assert rows[0]["operator_name"] == "sriov-network-operator"
    assert rows[0]["release_name"] == "25R3"


# -- tickets --

def test_create_ticket_and_exists(db, partner):
    db.create_ticket(partner["id"], "ECOPS-100", summary="Test ticket")
    assert db.ticket_exists(partner["id"], "ECOPS-100")
    assert not db.ticket_exists(partner["id"], "ECOPS-999")


def test_get_ticket_by_key(db, partner):
    db.create_ticket(partner["id"], "ECOPS-100", summary="Hello")
    t = db.get_ticket_by_key(partner["id"], "ECOPS-100")
    assert t["summary"] == "Hello"
    assert db.get_ticket_by_key(partner["id"], "ECOPS-999") is None


def test_update_ticket(db, partner):
    db.create_ticket(partner["id"], "ECOPS-100", summary="Old", resolution="")
    t = db.get_ticket_by_key(partner["id"], "ECOPS-100")
    db.update_ticket(t["id"], summary="New", resolution="Support Exception")
    updated = db.get_ticket_by_key(partner["id"], "ECOPS-100")
    assert updated["summary"] == "New"
    assert updated["resolution"] == "Support Exception"


# -- domains --

def test_create_domain(db, partner):
    d = db.create_domain(partner["id"], "networking", "Network config")
    assert d["name"] == "networking"
    assert db.list_domains(partner["id"])[0]["description"] == "Network config"


# -- knowledge --

def test_create_and_list_knowledge(db, partner):
    k = db.create_knowledge(partner["id"], "architecture", "SNO is used", detail="Single Node")
    assert k["fact"] == "SNO is used"
    items = db.list_knowledge(partner["id"])
    assert len(items) == 1


def test_list_knowledge_by_category(db, partner):
    db.create_knowledge(partner["id"], "architecture", "fact A")
    db.create_knowledge(partner["id"], "limitation", "fact B")
    arch = db.list_knowledge(partner["id"], category="architecture")
    assert len(arch) == 1 and arch[0]["fact"] == "fact A"


# -- partner_stats --

def test_partner_stats(db, partner, domain, release):
    db.create_ticket(partner["id"], "ECOPS-1")
    db.create_knowledge(partner["id"], "architecture", "fact")
    stats = db.partner_stats(partner["id"])
    assert stats["tickets"] == 1
    assert stats["domains"] == 1
    assert stats["releases"] == 1
    assert stats["knowledge"] == 1


# -- data_last_modified --

def test_data_last_modified_none_when_empty(db, partner):
    result = db.data_last_modified(partner["id"])
    assert result is None


def test_data_last_modified_after_ticket(db, partner):
    db.create_ticket(partner["id"], "ECOPS-1")
    assert db.data_last_modified(partner["id"]) is not None


# -- auth_source encryption --

def test_auth_source_encrypted(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TPS_MASTER_KEY", key)
    db = Database(tmp_path / "enc.db")
    p = db.create_partner("TestCo", "testco")
    db.create_auth_source(p["id"], "sharepoint.com", auth_value="my-cookie-value")
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "enc.db"))
    row = conn.execute("SELECT auth_value FROM auth_sources").fetchone()
    assert "my-cookie-value" not in row[0]
    conn.close()
    sources = db.list_auth_sources(p["id"])
    assert sources[0]["auth_value"] == "my-cookie-value"
