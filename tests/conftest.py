import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from tps.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


@pytest.fixture
def partner(db):
    return db.create_partner("Test Partner", "test-partner")


@pytest.fixture
def release(db, partner):
    return db.create_release(partner["id"], "25R3", ocp_version="4.17")


@pytest.fixture
def domain(db, partner):
    return db.create_domain(partner["id"], "networking")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TPS_SECRET", "")  # disable auth in tests
    monkeypatch.setattr("tps.app._DATA", tmp_path)
    monkeypatch.setattr("tps.app._OUTPUT", tmp_path / "output")
    monkeypatch.setattr("tps.app.db", Database(tmp_path / "partners.db"))
    from tps.app import app
    return TestClient(app)
