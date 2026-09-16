"""Backup and restore for TPS database + workspace."""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_EXPECTED_TABLES = {
    "partners", "topics", "knowledge", "ecops_tickets",
    "releases", "operators", "domains", "topic_notes",
}
_SKIP_NAMES = {".DS_Store", "__pycache__", ".claude"}
_WEEKLY_KEEP = 4


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _backup_db(source_conn: sqlite3.Connection, dest_path: Path) -> tuple[bool, str]:
    try:
        dest = sqlite3.connect(str(dest_path))
        source_conn.backup(dest)
        result = dest.execute("PRAGMA integrity_check").fetchone()[0]
        dest.close()
        if result != "ok":
            return False, f"Integrity check failed: {result}"
        return True, "ok"
    except Exception as e:
        return False, str(e)


def _add_dir_to_zip(zf: zipfile.ZipFile, src: Path, arc_prefix: str) -> None:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in _SKIP_NAMES]
        for f in files:
            if f in _SKIP_NAMES:
                continue
            full = Path(root) / f
            arc = f"{arc_prefix}/{full.relative_to(src)}"
            zf.write(full, arc)


def create_backup(
    db_conn: sqlite3.Connection,
    workspace_path: Path,
    dest_path: Path,
) -> tuple[bool, str]:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / "partners.db"
        ok, msg = _backup_db(db_conn, tmp_db)
        if not ok:
            return False, f"DB backup failed: {msg}"

        tmp_zip = Path(tmp) / "backup.zip"
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db, "partners.db")
            if workspace_path.is_dir():
                _add_dir_to_zip(zf, workspace_path, "workspace")

        shutil.move(str(tmp_zip), str(dest_path))

    ok, detail = validate_backup(dest_path)
    if not ok:
        dest_path.unlink(missing_ok=True)
        return False, f"Post-creation validation failed: {detail}"
    return True, str(dest_path)


def validate_backup(zip_path: Path) -> tuple[bool, str]:
    if not zip_path.is_file():
        return False, "File not found"
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if "partners.db" not in zf.namelist():
                return False, "Missing partners.db in archive"
    except zipfile.BadZipFile:
        return False, "Not a valid zip file"

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extract("partners.db", tmp)
        db_path = Path(tmp) / "partners.db"
        try:
            conn = sqlite3.connect(str(db_path))
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                conn.close()
                return False, f"Integrity check: {result}"
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            conn.close()
            missing = _EXPECTED_TABLES - tables
            if missing:
                return False, f"Missing tables: {', '.join(sorted(missing))}"
        except Exception as e:
            return False, f"DB validation error: {e}"
    return True, "ok"


def restore_backup(
    zip_path: Path,
    db: object,
    workspace_path: Path,
    backup_dir: Path,
) -> tuple[bool, str]:
    ok, detail = validate_backup(zip_path)
    if not ok:
        return False, f"Backup validation failed: {detail}"

    stamp = _now().strftime("%Y%m%d_%H%M%S")
    safety = backup_dir / f"pre_restore_{stamp}.zip"
    pre_ok, pre_msg = create_backup(db._conn, workspace_path, safety)
    if not pre_ok:
        log.warning("Pre-restore safety backup failed: %s", pre_msg)

    db._conn.close()

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            with tempfile.TemporaryDirectory() as tmp:
                zf.extractall(tmp)
                src_db = Path(tmp) / "partners.db"
                shutil.copy2(str(src_db), str(db._path))
                src_ws = Path(tmp) / "workspace"
                if src_ws.is_dir():
                    if workspace_path.exists():
                        shutil.rmtree(workspace_path)
                    shutil.copytree(str(src_ws), str(workspace_path))
    except Exception as e:
        # Re-open DB even on failure
        db.__init__(db._path)
        return False, f"Restore failed: {e}"

    db.__init__(db._path)
    return True, "Restored successfully"


def run_scheduled(
    db_conn: sqlite3.Connection,
    workspace_path: Path,
    backup_dir: Path,
) -> tuple[bool, str]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    now = _now()
    weekday = now.weekday()  # 0=Monday

    if weekday > 4:  # weekend
        return True, "Skipped (weekend)"

    if weekday == 0:
        dest = backup_dir / f"weekly_{now.strftime('%Y-%m-%d')}.zip"
        if dest.exists():
            return True, f"Already exists: {dest.name}"
        ok, msg = create_backup(db_conn, workspace_path, dest)
        if ok:
            _prune_weekly(backup_dir)
        return ok, msg
    else:
        dest = backup_dir / "daily.zip"
        return create_backup(db_conn, workspace_path, dest)


def _prune_weekly(backup_dir: Path) -> None:
    weeklies = sorted(backup_dir.glob("weekly_*.zip"), reverse=True)
    for old in weeklies[_WEEKLY_KEEP:]:
        old.unlink(missing_ok=True)
        log.info("Pruned old weekly backup: %s", old.name)


def list_backups(backup_dir: Path) -> list[dict]:
    if not backup_dir.is_dir():
        return []
    out = []
    for f in sorted(backup_dir.glob("*.zip"), reverse=True):
        stat = f.stat()
        if f.name.startswith("weekly_"):
            btype = "weekly"
        elif f.name == "daily.zip":
            btype = "daily"
        elif f.name.startswith("pre_restore_"):
            btype = "pre-restore"
        else:
            btype = "manual"
        out.append({
            "filename": f.name,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "created_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).astimezone().isoformat(timespec="seconds"),
            "type": btype,
        })
    return out
