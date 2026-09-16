from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _uuid() -> str:
    return str(uuid.uuid4())


def _fernet():
    key = os.environ.get("TPS_MASTER_KEY", "")
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def _enc(val: str) -> str:
    f = _fernet()
    return f.encrypt(val.encode()).decode() if f and val else val


def _dec(val: str) -> str:
    f = _fernet()
    if not f or not val:
        return val
    try:
        return f.decrypt(val.encode()).decode()
    except Exception:
        return val  # ponytail: plaintext fallback for existing unencrypted rows


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        if path.exists():
            os.chmod(path, 0o600)

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS partners (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                skill_version INTEGER NOT NULL DEFAULT 0,
                skill_generated_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS partner_jira_config (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                jira_url TEXT NOT NULL,
                jira_email TEXT NOT NULL,
                jira_token TEXT NOT NULL,
                project_key TEXT NOT NULL,
                version_prefix TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS releases (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                release_name TEXT NOT NULL,
                ocp_version TEXT NOT NULL DEFAULT '',
                partner_build TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operators (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                operator_name TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT '',
                current_version TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'redhat-operators',
                operator_status TEXT NOT NULL DEFAULT 'deployed',
                doc_url TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS release_operators (
                id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
                operator_id TEXT NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
                pinned_version TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(release_id, operator_id)
            );
            CREATE TABLE IF NOT EXISTS domains (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ecops_tickets (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                release_id TEXT REFERENCES releases(id) ON DELETE SET NULL,
                domain_id TEXT REFERENCES domains(id) ON DELETE SET NULL,
                ecops_key TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                resolution TEXT NOT NULL DEFAULT '',
                labels TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity_log (
                id TEXT PRIMARY KEY,
                partner_id TEXT REFERENCES partners(id) ON DELETE CASCADE,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topic_notes (
                id TEXT PRIMARY KEY,
                topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                note_type TEXT NOT NULL DEFAULT 'research',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topic_sources (
                id TEXT PRIMARY KEY,
                topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                url TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                source_tier INTEGER NOT NULL DEFAULT 4,
                content_extract TEXT NOT NULL DEFAULT '',
                accessed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topic_tickets (
                id TEXT PRIMARY KEY,
                topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                ticket_key TEXT NOT NULL,
                ticket_url TEXT NOT NULL DEFAULT '',
                relationship TEXT NOT NULL DEFAULT 'related',
                linked_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_sources (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                domain_pattern TEXT NOT NULL,
                auth_type TEXT NOT NULL DEFAULT 'cookie',
                auth_value TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL DEFAULT '',
                expires_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS doc_sources (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'sharepoint',
                base_url TEXT NOT NULL,
                path TEXT NOT NULL DEFAULT '',
                auth_source_id TEXT REFERENCES auth_sources(id) ON DELETE SET NULL,
                last_browsed_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
                category TEXT NOT NULL,
                fact TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                source_tier INTEGER NOT NULL DEFAULT 4,
                verified_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topic_results (
                id TEXT PRIMARY KEY,
                topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                result_type TEXT NOT NULL DEFAULT 'document',
                file_path TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learned_docs (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                doc_source_id TEXT REFERENCES doc_sources(id) ON DELETE SET NULL,
                url TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                folder_path TEXT NOT NULL DEFAULT '',
                content_extract TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
                learned_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topic_sessions (
                id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                claude_session_id TEXT NOT NULL UNIQUE,
                active_topic_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT
            );
            CREATE TABLE IF NOT EXISTS topic_interactions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES topic_sessions(id) ON DELETE CASCADE,
                topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                prompt TEXT NOT NULL,
                response TEXT,
                routed_by TEXT NOT NULL DEFAULT 'deterministic',
                confidence REAL,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );
        """)
        _migrate_cols = [
            ("partner_jira_config", "jira_mode", "TEXT NOT NULL DEFAULT 'mcp'"),
            ("partner_jira_config", "cloud_id", "TEXT NOT NULL DEFAULT ''"),
            ("topic_tickets", "summary", "TEXT NOT NULL DEFAULT ''"),
            ("topic_tickets", "jira_status", "TEXT NOT NULL DEFAULT ''"),
            ("releases", "ga_date", "TEXT NOT NULL DEFAULT ''"),
            ("releases", "eol_date", "TEXT NOT NULL DEFAULT ''"),
            ("releases", "doc_url", "TEXT NOT NULL DEFAULT ''"),
            ("releases", "release_status", "TEXT NOT NULL DEFAULT 'ga'"),
            ("partners", "skill_version", "INTEGER NOT NULL DEFAULT 0"),
            ("partners", "skill_generated_at", "TEXT"),
            ("learned_docs", "processing_status", "TEXT NOT NULL DEFAULT 'backlog'"),
            ("learned_docs", "modified_at", "TEXT NOT NULL DEFAULT ''"),
            ("knowledge", "status", "TEXT NOT NULL DEFAULT 'confirmed'"),
        ]
        for table, col, typedef in _migrate_cols:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        # Migrate ECOPS resolution proxies to actual meanings (Jira limitation workaround)
        _resolution_map = {
            "Done-Errata": "Support Exception",
            "Not a Bug": "Non-Impacting",
        }
        for old, new in _resolution_map.items():
            self._conn.execute(
                "UPDATE ecops_tickets SET resolution=? WHERE resolution=?", (new, old))
        # FTS5 for topic search
        try:
            self._conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS topics_fts USING fts5(
                    title, description, content=topics, content_rowid=rowid
                );
                -- Drop-and-recreate: earlier versions used `DELETE FROM topics_fts`,
                -- which is invalid for an external-content FTS5 table and leaves
                -- orphaned index rows (fts5: "missing row N from content table").
                -- The correct removal is the special 'delete' command below.
                DROP TRIGGER IF EXISTS topics_fts_insert;
                DROP TRIGGER IF EXISTS topics_fts_update;
                DROP TRIGGER IF EXISTS topics_fts_delete;
                CREATE TRIGGER topics_fts_insert AFTER INSERT ON topics BEGIN
                    INSERT INTO topics_fts(rowid, title, description)
                    VALUES (new.rowid, new.title, new.description);
                END;
                CREATE TRIGGER topics_fts_update AFTER UPDATE ON topics BEGIN
                    INSERT INTO topics_fts(topics_fts, rowid, title, description)
                    VALUES ('delete', old.rowid, old.title, old.description);
                    INSERT INTO topics_fts(rowid, title, description)
                    VALUES (new.rowid, new.title, new.description);
                END;
                CREATE TRIGGER topics_fts_delete AFTER DELETE ON topics BEGIN
                    INSERT INTO topics_fts(topics_fts, rowid, title, description)
                    VALUES ('delete', old.rowid, old.title, old.description);
                END;
            """)
            # Rebuild FTS from topics whenever the counts disagree — repairs any
            # desync left by the old buggy triggers.
            existing = self._conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
            fts_count = self._conn.execute("SELECT COUNT(*) FROM topics_fts").fetchone()[0]
            if existing != fts_count:
                self._conn.execute("INSERT INTO topics_fts(topics_fts) VALUES('rebuild')")
        except Exception:
            pass
        self._conn.commit()

    # -- app settings --

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        r = self._conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)", (key, value)
        )
        self._conn.commit()

    # -- partners --

    def create_partner(self, name: str, slug: str) -> dict:
        now = _utc_now_iso()
        pid = _uuid()
        self._conn.execute(
            "INSERT INTO partners (id, name, slug, created_at, updated_at) VALUES (?,?,?,?,?)",
            (pid, name, slug, now, now),
        )
        self._conn.commit()
        self._log(pid, "created", f"Partner '{name}' created")
        return self.get_partner(pid)

    def get_partner(self, pid: str) -> dict | None:
        r = self._conn.execute("SELECT * FROM partners WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

    def get_partner_by_slug(self, slug: str) -> dict | None:
        r = self._conn.execute("SELECT * FROM partners WHERE slug=?", (slug,)).fetchone()
        return dict(r) if r else None

    def list_partners(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM partners ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def update_partner(self, pid: str, **fields) -> None:
        allowed = {"name", "slug"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        sets["updated_at"] = _utc_now_iso()
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE partners SET {clause} WHERE id=?", (*sets.values(), pid))
        self._conn.commit()

    def delete_partner(self, pid: str) -> None:
        self._conn.execute("DELETE FROM partners WHERE id=?", (pid,))
        self._conn.commit()

    def bump_skill_version(self, pid: str) -> int:
        now = _utc_now_iso()
        self._conn.execute(
            "UPDATE partners SET skill_version = skill_version + 1, skill_generated_at = ?, updated_at = ? WHERE id = ?",
            (now, now, pid),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT skill_version FROM partners WHERE id=?", (pid,)).fetchone()
        return row["skill_version"] if row else 0

    # -- jira config --

    def set_jira_config(self, partner_id: str, jira_url: str, jira_email: str,
                        jira_token: str, project_key: str, version_prefix: str,
                        jira_mode: str = "mcp", cloud_id: str = "") -> dict:
        self._conn.execute("DELETE FROM partner_jira_config WHERE partner_id=?", (partner_id,))
        cid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO partner_jira_config (id, partner_id, jira_url, jira_email, jira_token, project_key, version_prefix, created_at, jira_mode, cloud_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, partner_id, jira_url, jira_email, _enc(jira_token), project_key, version_prefix, now, jira_mode, cloud_id),
        )
        self._conn.commit()
        self._log(partner_id, "jira_configured", f"Jira configured: {jira_mode} / {project_key}")
        return self.get_jira_config(partner_id)

    def get_jira_config(self, partner_id: str) -> dict | None:
        r = self._conn.execute(
            "SELECT * FROM partner_jira_config WHERE partner_id=?", (partner_id,)
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        d["jira_token"] = _dec(d["jira_token"])
        return d

    # -- releases --

    def create_release(self, partner_id: str, release_name: str,
                       ocp_version: str = "", partner_build: str = "",
                       ga_date: str = "", eol_date: str = "",
                       doc_url: str = "", release_status: str = "ga") -> dict:
        rid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO releases (id, partner_id, release_name, ocp_version, partner_build, created_at, ga_date, eol_date, doc_url, release_status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, partner_id, release_name, ocp_version, partner_build, now, ga_date, eol_date, doc_url, release_status),
        )
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM releases WHERE id=?", (rid,)).fetchone())

    def list_releases(self, partner_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM releases WHERE partner_id=? ORDER BY release_name", (partner_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_release(self, rid: str, **fields) -> None:
        allowed = {"release_name", "ocp_version", "partner_build", "ga_date", "eol_date", "doc_url", "release_status"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE releases SET {clause} WHERE id=?", (*sets.values(), rid))
        self._conn.commit()

    def delete_release(self, rid: str) -> None:
        self._conn.execute("DELETE FROM releases WHERE id=?", (rid,))
        self._conn.commit()

    # -- operators --

    def create_operator(self, partner_id: str, operator_name: str,
                        channel: str = "", current_version: str = "",
                        source: str = "redhat-operators",
                        operator_status: str = "deployed",
                        doc_url: str = "", notes: str = "") -> dict:
        oid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO operators (id, partner_id, operator_name, channel, current_version, "
            "source, operator_status, doc_url, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (oid, partner_id, operator_name, channel, current_version,
             source, operator_status, doc_url, notes, now),
        )
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM operators WHERE id=?", (oid,)).fetchone())

    def list_operators(self, partner_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM operators WHERE partner_id=? ORDER BY operator_name", (partner_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_operator(self, oid: str, **fields) -> None:
        allowed = {"operator_name", "channel", "current_version", "source", "operator_status", "doc_url", "notes"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE operators SET {clause} WHERE id=?", (*sets.values(), oid))
        self._conn.commit()

    def delete_operator(self, oid: str) -> None:
        self._conn.execute("DELETE FROM operators WHERE id=?", (oid,))
        self._conn.commit()

    # -- release-operator version pins --

    def pin_operator_version(self, release_id: str, operator_id: str, pinned_version: str) -> dict:
        now = _utc_now_iso()
        pid = _uuid()
        self._conn.execute(
            "INSERT INTO release_operators (id, release_id, operator_id, pinned_version, created_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(release_id, operator_id) DO UPDATE SET pinned_version=excluded.pinned_version",
            (pid, release_id, operator_id, pinned_version, now),
        )
        self._conn.commit()
        r = self._conn.execute(
            "SELECT * FROM release_operators WHERE release_id=? AND operator_id=?",
            (release_id, operator_id),
        ).fetchone()
        return dict(r)

    def get_operator_pins(self, operator_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ro.*, r.release_name, r.ocp_version "
            "FROM release_operators ro JOIN releases r ON ro.release_id = r.id "
            "WHERE ro.operator_id=? ORDER BY r.release_name",
            (operator_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_release_operators(self, partner_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ro.*, r.release_name, r.ocp_version, o.operator_name "
            "FROM release_operators ro "
            "JOIN releases r ON ro.release_id = r.id "
            "JOIN operators o ON ro.operator_id = o.id "
            "WHERE r.partner_id=? ORDER BY r.release_name, o.operator_name",
            (partner_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_operator_pin(self, pin_id: str) -> None:
        self._conn.execute("DELETE FROM release_operators WHERE id=?", (pin_id,))
        self._conn.commit()

    # -- domains --

    def create_domain(self, partner_id: str, name: str, description: str = "") -> dict:
        did = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO domains (id, partner_id, name, description, created_at) VALUES (?,?,?,?,?)",
            (did, partner_id, name, description, now),
        )
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM domains WHERE id=?", (did,)).fetchone())

    def list_domains(self, partner_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM domains WHERE partner_id=? ORDER BY name", (partner_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_domain(self, did: str, **fields) -> None:
        allowed = {"name", "description"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE domains SET {clause} WHERE id=?", (*sets.values(), did))
        self._conn.commit()

    def delete_domain(self, did: str) -> None:
        self._conn.execute("DELETE FROM domains WHERE id=?", (did,))
        self._conn.commit()

    # -- ecops tickets --

    def create_ticket(self, partner_id: str, ecops_key: str, summary: str = "",
                      resolution: str = "", labels: str = "", raw_json: str = "{}",
                      release_id: str | None = None, domain_id: str | None = None) -> dict:
        tid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO ecops_tickets (id, partner_id, release_id, domain_id, ecops_key, summary, resolution, labels, raw_json, imported_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (tid, partner_id, release_id, domain_id, ecops_key, summary, resolution, labels, raw_json, now),
        )
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM ecops_tickets WHERE id=?", (tid,)).fetchone())

    def list_tickets(self, partner_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT t.*, r.release_name, dm.name as domain_name "
            "FROM ecops_tickets t "
            "LEFT JOIN releases r ON t.release_id = r.id "
            "LEFT JOIN domains dm ON t.domain_id = dm.id "
            "WHERE t.partner_id=? ORDER BY t.ecops_key",
            (partner_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_ticket(self, tid: str, **fields) -> None:
        allowed = {"release_id", "domain_id", "summary", "resolution", "labels"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE ecops_tickets SET {clause} WHERE id=?", (*sets.values(), tid))
        self._conn.commit()

    def delete_ticket(self, tid: str) -> None:
        self._conn.execute("DELETE FROM ecops_tickets WHERE id=?", (tid,))
        self._conn.commit()

    def ticket_exists(self, partner_id: str, ecops_key: str) -> bool:
        r = self._conn.execute(
            "SELECT 1 FROM ecops_tickets WHERE partner_id=? AND ecops_key=?",
            (partner_id, ecops_key),
        ).fetchone()
        return r is not None

    def get_ticket_by_key(self, partner_id: str, ecops_key: str) -> dict | None:
        r = self._conn.execute(
            "SELECT * FROM ecops_tickets WHERE partner_id=? AND ecops_key=?",
            (partner_id, ecops_key),
        ).fetchone()
        return dict(r) if r else None

    # -- topics --

    def create_topic(self, partner_id: str, title: str, description: str = "",
                     status: str = "open") -> dict:
        tid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO topics (id, partner_id, title, status, description, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (tid, partner_id, title, status, description, now, now),
        )
        self._conn.commit()
        self._log(partner_id, "topic_created", f"Topic: {title}")
        return dict(self._conn.execute("SELECT * FROM topics WHERE id=?", (tid,)).fetchone())

    def get_topic(self, tid: str) -> dict | None:
        r = self._conn.execute("SELECT * FROM topics WHERE id=?", (tid,)).fetchone()
        return dict(r) if r else None

    def list_topics(self, partner_id: str, status: str | None = None) -> list[dict]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM topics WHERE partner_id=? AND status=? ORDER BY updated_at DESC",
                (partner_id, status),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM topics WHERE partner_id=? ORDER BY updated_at DESC",
                (partner_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_topic(self, tid: str, **fields) -> None:
        allowed = {"title", "status", "description"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        sets["updated_at"] = _utc_now_iso()
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE topics SET {clause} WHERE id=?", (*sets.values(), tid))
        self._conn.commit()

    def delete_topic(self, tid: str) -> None:
        self._conn.execute("DELETE FROM topics WHERE id=?", (tid,))
        self._conn.commit()

    # Child tables that carry a topic_id and should follow a merge.
    _TOPIC_CHILD_TABLES = (
        "topic_interactions", "topic_notes", "topic_sources",
        "topic_results", "topic_tickets", "knowledge",
    )

    def merge_topics(self, src_ids: list[str], dest_id: str) -> dict:
        """Fold one or more source topics into dest_id, then delete them.

        Reassigns all child rows (interactions, notes, sources, results,
        tickets, knowledge) and repoints any session whose active topic was a
        source. FTS is trigger-maintained, so deleting the source rows cleans it.
        Returns a per-table count of rows moved.
        """
        src = [s for s in src_ids if s and s != dest_id]
        if not src:
            return {}
        if not self.get_topic(dest_id):
            raise ValueError(f"dest topic {dest_id} does not exist")
        placeholders = ",".join("?" * len(src))
        moved: dict[str, int] = {}
        for table in self._TOPIC_CHILD_TABLES:
            cur = self._conn.execute(
                f"UPDATE {table} SET topic_id=? WHERE topic_id IN ({placeholders})",
                (dest_id, *src),
            )
            moved[table] = cur.rowcount
        self._conn.execute(
            f"UPDATE topic_sessions SET active_topic_id=? "
            f"WHERE active_topic_id IN ({placeholders})",
            (dest_id, *src),
        )
        self._conn.execute(
            f"DELETE FROM topics WHERE id IN ({placeholders})", tuple(src)
        )
        self._conn.execute(
            "UPDATE topics SET updated_at=? WHERE id=?", (_utc_now_iso(), dest_id)
        )
        self._conn.commit()
        return moved

    def search_topics_fts(self, partner_id: str, query: str, limit: int = 5) -> list[dict]:
        import re as _re
        # Sanitize for FTS5: strip non-word chars, quote each term
        clean = _re.sub(r'[^\w\s]', ' ', query).strip()
        terms = [f'"{t}"' for t in clean.split() if len(t) > 1]
        if not terms:
            return []
        fts_query = " OR ".join(terms)
        rows = self._conn.execute(
            "SELECT t.*, rank FROM topics_fts f "
            "JOIN topics t ON t.rowid = f.rowid "
            "WHERE topics_fts MATCH ? AND t.partner_id = ? "
            "ORDER BY rank LIMIT ?",
            (fts_query, partner_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- topic sessions --

    def create_topic_session(self, partner_id: str, claude_session_id: str) -> dict:
        sid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT OR IGNORE INTO topic_sessions "
            "(id, partner_id, claude_session_id, started_at) VALUES (?,?,?,?)",
            (sid, partner_id, claude_session_id, now),
        )
        self._conn.commit()
        return self.get_topic_session_by_claude_id(claude_session_id)

    def get_topic_session_by_claude_id(self, claude_session_id: str) -> dict | None:
        r = self._conn.execute(
            "SELECT * FROM topic_sessions WHERE claude_session_id=?",
            (claude_session_id,),
        ).fetchone()
        return dict(r) if r else None

    def update_topic_session(self, session_id: str, **fields) -> None:
        allowed = {"active_topic_id", "ended_at"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(
            f"UPDATE topic_sessions SET {clause} WHERE id=?", (*sets.values(), session_id)
        )
        self._conn.commit()

    # -- topic interactions --

    def create_topic_interaction(self, session_id: str, topic_id: str,
                                 prompt: str, routed_by: str = "deterministic",
                                 confidence: float | None = None) -> dict:
        iid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO topic_interactions "
            "(id, session_id, topic_id, prompt, routed_by, confidence, started_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (iid, session_id, topic_id, prompt, routed_by, confidence, now),
        )
        self._conn.execute("UPDATE topics SET updated_at=? WHERE id=?", (now, topic_id))
        self._conn.commit()
        return dict(self._conn.execute(
            "SELECT * FROM topic_interactions WHERE id=?", (iid,)
        ).fetchone())

    def complete_topic_interaction(self, interaction_id: str, response: str) -> None:
        now = _utc_now_iso()
        self._conn.execute(
            "UPDATE topic_interactions SET response=?, completed_at=? WHERE id=?",
            (response, now, interaction_id),
        )
        # Update parent topic timestamp
        row = self._conn.execute(
            "SELECT topic_id FROM topic_interactions WHERE id=?", (interaction_id,)
        ).fetchone()
        if row:
            self._conn.execute("UPDATE topics SET updated_at=? WHERE id=?", (now, row["topic_id"]))
        self._conn.commit()

    def get_latest_interaction(self, session_id: str) -> dict | None:
        r = self._conn.execute(
            "SELECT * FROM topic_interactions WHERE session_id=? "
            "ORDER BY started_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return dict(r) if r else None

    def list_topic_interactions(self, topic_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM topic_interactions WHERE topic_id=? ORDER BY started_at",
            (topic_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- topic notes --

    def create_topic_note(self, topic_id: str, content: str,
                          note_type: str = "research") -> dict:
        nid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO topic_notes (id, topic_id, content, note_type, created_at) VALUES (?,?,?,?,?)",
            (nid, topic_id, content, note_type, now),
        )
        self._conn.execute("UPDATE topics SET updated_at=? WHERE id=?", (now, topic_id))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM topic_notes WHERE id=?", (nid,)).fetchone())

    def list_topic_notes(self, topic_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM topic_notes WHERE topic_id=? ORDER BY created_at DESC",
            (topic_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_topic_note(self, nid: str) -> None:
        self._conn.execute("DELETE FROM topic_notes WHERE id=?", (nid,))
        self._conn.commit()

    # -- topic sources --

    def create_topic_source(self, topic_id: str, url: str, title: str = "",
                            source_tier: int = 4, content_extract: str = "") -> dict:
        sid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO topic_sources (id, topic_id, url, title, source_tier, content_extract, accessed_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (sid, topic_id, url, title, source_tier, content_extract, now),
        )
        self._conn.execute("UPDATE topics SET updated_at=? WHERE id=?", (now, topic_id))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM topic_sources WHERE id=?", (sid,)).fetchone())

    def list_topic_sources(self, topic_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM topic_sources WHERE topic_id=? ORDER BY accessed_at DESC",
            (topic_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_topic_source(self, sid: str, **fields) -> None:
        allowed = {"title", "source_tier", "content_extract"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE topic_sources SET {clause} WHERE id=?", (*sets.values(), sid))
        self._conn.commit()

    def delete_topic_source(self, sid: str) -> None:
        self._conn.execute("DELETE FROM topic_sources WHERE id=?", (sid,))
        self._conn.commit()

    # -- topic results --

    def create_topic_result(self, topic_id: str, title: str, description: str = "",
                            result_type: str = "document", file_path: str = "",
                            url: str = "") -> dict:
        rid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO topic_results (id, topic_id, title, description, result_type, file_path, url, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (rid, topic_id, title, description, result_type, file_path, url, now),
        )
        self._conn.execute("UPDATE topics SET updated_at=? WHERE id=?", (now, topic_id))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM topic_results WHERE id=?", (rid,)).fetchone())

    def list_topic_results(self, topic_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM topic_results WHERE topic_id=? ORDER BY created_at DESC",
            (topic_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_topic_result(self, rid: str) -> None:
        self._conn.execute("DELETE FROM topic_results WHERE id=?", (rid,))
        self._conn.commit()

    # -- topic tickets --

    def link_topic_ticket(self, topic_id: str, ticket_key: str,
                          ticket_url: str = "", relationship: str = "related",
                          summary: str = "", jira_status: str = "") -> dict:
        lid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO topic_tickets (id, topic_id, ticket_key, ticket_url, relationship, linked_at, summary, jira_status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (lid, topic_id, ticket_key, ticket_url, relationship, now, summary, jira_status),
        )
        self._conn.execute("UPDATE topics SET updated_at=? WHERE id=?", (now, topic_id))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM topic_tickets WHERE id=?", (lid,)).fetchone())

    def list_topic_tickets(self, topic_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM topic_tickets WHERE topic_id=? ORDER BY linked_at DESC",
            (topic_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def unlink_topic_ticket(self, lid: str) -> None:
        self._conn.execute("DELETE FROM topic_tickets WHERE id=?", (lid,))
        self._conn.commit()

    # -- knowledge --

    def create_knowledge(self, partner_id: str, category: str, fact: str,
                         detail: str = "", source_url: str = "", source_tier: int = 4,
                         topic_id: str | None = None, verified_at: str | None = None,
                         status: str = "confirmed") -> dict:
        kid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO knowledge (id, partner_id, topic_id, category, fact, detail, source_url, source_tier, verified_at, created_at, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (kid, partner_id, topic_id, category, fact, detail, source_url, source_tier, verified_at, now, status),
        )
        self._conn.commit()
        self._log(partner_id, "knowledge_added", f"[{category}] {fact[:80]}")
        return dict(self._conn.execute("SELECT * FROM knowledge WHERE id=?", (kid,)).fetchone())

    def list_knowledge(self, partner_id: str, category: str | None = None,
                       status: str | None = None) -> list[dict]:
        clauses = ["partner_id=?"]
        params: list = [partner_id]
        if category:
            clauses.append("category=?")
            params.append(category)
        if status:
            clauses.append("status=?")
            params.append(status)
        where = " AND ".join(clauses)
        rows = self._conn.execute(
            f"SELECT * FROM knowledge WHERE {where} ORDER BY category, created_at DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def update_knowledge(self, kid: str, **fields) -> None:
        allowed = {"category", "fact", "detail", "source_url", "source_tier", "verified_at", "status"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE knowledge SET {clause} WHERE id=?", (*sets.values(), kid))
        self._conn.commit()

    def delete_knowledge(self, kid: str) -> None:
        self._conn.execute("DELETE FROM knowledge WHERE id=?", (kid,))
        self._conn.commit()

    # -- doc sources --

    def create_doc_source(self, partner_id: str, name: str, source_type: str = "sharepoint",
                          base_url: str = "", path: str = "",
                          auth_source_id: str | None = None) -> dict:
        dsid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO doc_sources (id, partner_id, name, source_type, base_url, path, auth_source_id, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (dsid, partner_id, name, source_type, base_url, path, auth_source_id, now),
        )
        self._conn.commit()
        self._log(partner_id, "doc_source_added", f"Doc source: {name} ({source_type})")
        return dict(self._conn.execute("SELECT * FROM doc_sources WHERE id=?", (dsid,)).fetchone())

    def list_doc_sources(self, partner_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ds.*, a.domain_pattern as auth_domain, a.label as auth_label "
            "FROM doc_sources ds LEFT JOIN auth_sources a ON ds.auth_source_id = a.id "
            "WHERE ds.partner_id=? ORDER BY ds.name",
            (partner_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_doc_source(self, dsid: str) -> dict | None:
        r = self._conn.execute("SELECT * FROM doc_sources WHERE id=?", (dsid,)).fetchone()
        return dict(r) if r else None

    def update_doc_source(self, dsid: str, **fields) -> None:
        allowed = {"name", "source_type", "base_url", "path", "auth_source_id", "last_browsed_at"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE doc_sources SET {clause} WHERE id=?", (*sets.values(), dsid))
        self._conn.commit()

    def delete_doc_source(self, dsid: str) -> None:
        self._conn.execute("DELETE FROM doc_sources WHERE id=?", (dsid,))
        self._conn.commit()

    # -- auth sources --

    def create_auth_source(self, partner_id: str, domain_pattern: str,
                           auth_type: str = "cookie", auth_value: str = "",
                           label: str = "", expires_at: str | None = None) -> dict:
        aid = _uuid()
        now = _utc_now_iso()
        self._conn.execute(
            "INSERT INTO auth_sources (id, partner_id, domain_pattern, auth_type, auth_value, label, expires_at, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (aid, partner_id, domain_pattern, auth_type, _enc(auth_value), label, expires_at, now),
        )
        self._conn.commit()
        r = dict(self._conn.execute("SELECT * FROM auth_sources WHERE id=?", (aid,)).fetchone())
        r["auth_value"] = _dec(r["auth_value"])
        return r

    def list_auth_sources(self, partner_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM auth_sources WHERE partner_id=? ORDER BY domain_pattern",
            (partner_id,),
        ).fetchall()
        result = [dict(r) for r in rows]
        for r in result:
            r["auth_value"] = _dec(r["auth_value"])
        return result

    def get_auth_for_domain(self, partner_id: str, domain: str) -> dict | None:
        rows = self._conn.execute(
            "SELECT * FROM auth_sources WHERE partner_id=? ORDER BY length(domain_pattern) DESC",
            (partner_id,),
        ).fetchall()
        for r in rows:
            if r["domain_pattern"] in domain:
                d = dict(r)
                d["auth_value"] = _dec(d["auth_value"])
                return d
        return None

    def update_auth_source(self, aid: str, **fields) -> None:
        allowed = {"domain_pattern", "auth_type", "auth_value", "label", "expires_at"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        if "auth_value" in sets:
            sets["auth_value"] = _enc(sets["auth_value"])
        clause = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE auth_sources SET {clause} WHERE id=?", (*sets.values(), aid))
        self._conn.commit()

    def delete_auth_source(self, aid: str) -> None:
        self._conn.execute("DELETE FROM auth_sources WHERE id=?", (aid,))
        self._conn.commit()

    # -- learned docs --

    def create_or_update_learned_doc(self, partner_id: str, doc_source_id: str | None,
                                     url: str, name: str, folder_path: str = "",
                                     content_extract: str = "", file_size: int = 0,
                                     modified_at: str = "") -> dict:
        now = _utc_now_iso()
        existing = self._conn.execute("SELECT id FROM learned_docs WHERE url=?", (url,)).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE learned_docs SET name=?, folder_path=?, content_extract=?, "
                "file_size=?, learned_at=?, modified_at=? WHERE id=?",
                (name, folder_path, content_extract, file_size, now, modified_at, existing["id"]),
            )
            self._conn.commit()
            return dict(self._conn.execute("SELECT * FROM learned_docs WHERE id=?",
                                           (existing["id"],)).fetchone())
        lid = _uuid()
        self._conn.execute(
            "INSERT INTO learned_docs (id, partner_id, doc_source_id, url, name, "
            "folder_path, content_extract, file_size, learned_at, modified_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (lid, partner_id, doc_source_id, url, name, folder_path,
             content_extract, file_size, now, modified_at),
        )
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM learned_docs WHERE id=?", (lid,)).fetchone())

    def list_learned_docs(self, partner_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM learned_docs WHERE partner_id=? ORDER BY folder_path, name",
            (partner_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_learned_docs_by_source(self, doc_source_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM learned_docs WHERE doc_source_id=? ORDER BY folder_path, name",
            (doc_source_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def learned_urls_for_source(self, doc_source_id: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT url FROM learned_docs WHERE doc_source_id=?", (doc_source_id,),
        ).fetchall()
        return {r["url"] for r in rows}

    def learned_docs_stats_by_source(self, partner_id: str) -> dict:
        rows = self._conn.execute(
            "SELECT doc_source_id, COUNT(*) as count, MAX(learned_at) as last_learned_at "
            "FROM learned_docs WHERE partner_id=? GROUP BY doc_source_id",
            (partner_id,),
        ).fetchall()
        return {r["doc_source_id"]: {"count": r["count"], "last_learned_at": r["last_learned_at"]} for r in rows}

    def count_learned_docs(self, partner_id: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM learned_docs WHERE partner_id=?", (partner_id,),
        ).fetchone()[0]

    def delete_learned_doc(self, lid: str) -> None:
        self._conn.execute("DELETE FROM learned_docs WHERE id=?", (lid,))
        self._conn.commit()

    def update_learned_doc_status(self, lid: str, status: str) -> None:
        self._conn.execute("UPDATE learned_docs SET processing_status=? WHERE id=?", (status, lid))
        self._conn.commit()

    def bulk_update_learned_doc_status(self, lids: list[str], status: str) -> int:
        if not lids:
            return 0
        placeholders = ",".join("?" for _ in lids)
        cur = self._conn.execute(
            f"UPDATE learned_docs SET processing_status=? WHERE id IN ({placeholders})",
            (status, *lids),
        )
        self._conn.commit()
        return cur.rowcount

    def list_learned_docs_by_status(self, partner_id: str, status: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM learned_docs WHERE partner_id=? AND processing_status=? ORDER BY learned_at DESC",
            (partner_id, status),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_learned_docs_by_status(self, partner_id: str) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT processing_status, COUNT(*) as cnt FROM learned_docs WHERE partner_id=? GROUP BY processing_status",
            (partner_id,),
        ).fetchall()
        return {r["processing_status"]: r["cnt"] for r in rows}

    # -- activity log --

    def _log(self, partner_id: str | None, action: str, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO activity_log (id, partner_id, action, detail, created_at) VALUES (?,?,?,?,?)",
            (_uuid(), partner_id, action, detail, _utc_now_iso()),
        )
        self._conn.commit()

    def log(self, partner_id: str | None, action: str, detail: str = "") -> None:
        self._log(partner_id, action, detail)

    def list_activity(self, limit: int = 50, partner_id: str | None = None) -> list[dict]:
        if partner_id:
            rows = self._conn.execute(
                "SELECT a.*, p.name as partner_name FROM activity_log a "
                "LEFT JOIN partners p ON a.partner_id = p.id "
                "WHERE a.partner_id=? ORDER BY a.created_at DESC LIMIT ?",
                (partner_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT a.*, p.name as partner_name FROM activity_log a "
                "LEFT JOIN partners p ON a.partner_id = p.id "
                "ORDER BY a.created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- stats --

    def data_last_modified(self, pid: str) -> str | None:
        r = self._conn.execute("""
            SELECT MAX(ts) FROM (
                SELECT COALESCE(MAX(imported_at), '') ts FROM ecops_tickets WHERE partner_id=?
                UNION ALL SELECT COALESCE(MAX(created_at), '') FROM knowledge WHERE partner_id=?
                UNION ALL SELECT COALESCE(MAX(created_at), '') FROM operators WHERE partner_id=?
                UNION ALL SELECT COALESCE(MAX(created_at), '') FROM releases WHERE partner_id=?
            )
        """, (pid, pid, pid, pid)).fetchone()
        return r[0] or None

    def partner_stats(self, pid: str) -> dict:
        tickets = self._conn.execute(
            "SELECT COUNT(*) FROM ecops_tickets WHERE partner_id=?", (pid,)
        ).fetchone()[0]
        domains = self._conn.execute(
            "SELECT COUNT(*) FROM domains WHERE partner_id=?", (pid,)
        ).fetchone()[0]
        releases = self._conn.execute(
            "SELECT COUNT(*) FROM releases WHERE partner_id=?", (pid,)
        ).fetchone()[0]
        uncategorised = self._conn.execute(
            "SELECT COUNT(*) FROM ecops_tickets WHERE partner_id=? AND domain_id IS NULL", (pid,)
        ).fetchone()[0]
        topics = self._conn.execute(
            "SELECT COUNT(*) FROM topics WHERE partner_id=?", (pid,)
        ).fetchone()[0]
        knowledge_count = self._conn.execute(
            "SELECT COUNT(*) FROM knowledge WHERE partner_id=?", (pid,)
        ).fetchone()[0]
        learned_docs = self._conn.execute(
            "SELECT COUNT(*) FROM learned_docs WHERE partner_id=?", (pid,)
        ).fetchone()[0]
        operators = self._conn.execute(
            "SELECT COUNT(*) FROM operators WHERE partner_id=?", (pid,)
        ).fetchone()[0]
        return {
            "tickets": tickets, "domains": domains, "releases": releases,
            "uncategorised": uncategorised,
            "topics": topics, "knowledge": knowledge_count,
            "learned_docs": learned_docs, "operators": operators,
        }
