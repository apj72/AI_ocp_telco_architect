import sqlite3
import zipfile

import pytest

from tps.backup import create_backup, list_backups, restore_backup, validate_backup
from tps.db import Database


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "data" / "partners.db")
    db._conn.execute("INSERT INTO partners (id, name, slug, created_at, updated_at) VALUES ('p1', 'TestCo', 'testco', '2026-01-01', '2026-01-01')")
    db._conn.commit()
    ws = tmp_path / "workspace" / "topics" / "t1" / "results"
    ws.mkdir(parents=True)
    (ws / "report.md").write_text("# Test report")
    backup_dir = tmp_path / "backups"
    return db, tmp_path / "workspace", backup_dir


def test_create_and_validate(env):
    db, ws, backup_dir = env
    dest = backup_dir / "test.zip"
    ok, msg = create_backup(db._conn, ws, dest)
    assert ok, msg
    assert dest.is_file()
    ok2, detail = validate_backup(dest)
    assert ok2, detail
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
        assert "partners.db" in names
        assert any("report.md" in n for n in names)


def test_validate_bad_zip(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    ok, detail = validate_backup(bad)
    assert not ok
    assert "valid zip" in detail.lower()


def test_validate_missing_db(tmp_path):
    zp = tmp_path / "nodb.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("readme.txt", "no db here")
    ok, detail = validate_backup(zp)
    assert not ok
    assert "Missing partners.db" in detail


def test_restore(env):
    db, ws, backup_dir = env
    dest = backup_dir / "restore_test.zip"
    create_backup(db._conn, ws, dest)
    db._conn.execute("DELETE FROM partners WHERE id='p1'")
    db._conn.commit()
    assert db._conn.execute("SELECT count(*) FROM partners").fetchone()[0] == 0
    ok, msg = restore_backup(dest, db, ws, backup_dir)
    assert ok, msg
    assert db._conn.execute("SELECT count(*) FROM partners").fetchone()[0] == 1


def test_list_backups(env):
    db, ws, backup_dir = env
    backup_dir.mkdir(parents=True)
    for name in ["daily.zip", "weekly_2026-07-28.zip", "manual_20260728.zip"]:
        dest = backup_dir / name
        create_backup(db._conn, ws, dest)
    items = list_backups(backup_dir)
    assert len(items) == 3
    types = {i["type"] for i in items}
    assert types == {"daily", "weekly", "manual"}
