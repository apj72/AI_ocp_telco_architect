from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import logging
import threading

from tps.db import Database, _utc_now_iso
from tps.backup import create_backup, list_backups, restore_backup, run_scheduled, validate_backup
from tps.jira_import import import_from_jira, suggest_domains, jira_search, jira_get_issue, jira_create_issue
from tps.ocp_versions import fetch_ocp_releases
from tps.doc_browse import browse_doc_source
from tps.research import fetch_and_extract
from tps.skill_gen import generate_skill
from tps.terminal import terminal_handler
from tps.topic_router import route_prompt, _derive_title, _recent_open_topics

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data"
_TEMPLATES = _ROOT / "templates"
_STATIC = _ROOT / "static"
_DEFAULT_OUTPUT = _ROOT / "output"
_WORKSPACE = Path(os.environ.get("TPS_WORKSPACE", Path.home() / "tps-workspace"))
_BACKUP_DIR = _DATA / "backups"

app = FastAPI(title="Telco Partner Skills", version="0.1.0")
templates = Jinja2Templates(directory=str(_TEMPLATES))
db = Database(_DATA / "partners.db")

_SECRET = os.environ.get("TPS_SECRET", "")
_AUTH_EXEMPT = {"/login", "/health"}


def _output_dir() -> Path:
    custom = db.get_setting("output_path")
    return Path(custom) if custom else _DEFAULT_OUTPUT


_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = _CSP
    return response


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    if not _SECRET:
        return await call_next(request)
    path = request.url.path
    if path in _AUTH_EXEMPT or path.startswith("/static/"):
        return await call_next(request)
    if request.cookies.get("tps_auth") != _SECRET:
        if request.headers.get("upgrade", "").lower() == "websocket":
            return Response(status_code=403)
        return RedirectResponse("/login")
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/login")
async def login_submit(request: Request, secret: str = Form(...)) -> Response:
    if not _SECRET or secret != _SECRET:
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid password"}, status_code=401)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("tps_auth", secret, httponly=True, samesite="strict")
    return resp


@app.post("/api/logout")
def logout() -> Response:
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("tps_auth")
    return resp


def ensure_topic_workspace(tid: str) -> Path:
    base = _WORKSPACE / "topics" / tid
    for sub in ("results", "working", "research"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


@app.on_event("startup")
def startup():
    (_WORKSPACE / "topics").mkdir(parents=True, exist_ok=True)
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_run_scheduled_backup, daemon=True).start()


def _run_scheduled_backup():
    try:
        ok, msg = run_scheduled(db._conn, _WORKSPACE, _BACKUP_DIR)
        logging.getLogger(__name__).info("Scheduled backup: %s — %s", "OK" if ok else "FAIL", msg)
    except Exception as e:
        logging.getLogger(__name__).warning("Scheduled backup error: %s", e)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# -- Dashboard --

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    partners = db.list_partners()
    for p in partners:
        p["stats"] = db.partner_stats(p["id"])
        cfg = db.get_jira_config(p["id"])
        if cfg:
            cfg.pop("jira_token", None)
        p["jira_config"] = cfg
    activity = db.list_activity(limit=20)
    return templates.TemplateResponse(request, "index.html", {
        "partners": partners, "activity": activity,
    })


# -- Partner CRUD --

@app.post("/api/partners")
def create_partner(name: str = Form(...)) -> JSONResponse:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise HTTPException(400, "Invalid name")
    if db.get_partner_by_slug(slug):
        raise HTTPException(409, f"Partner '{slug}' already exists")
    p = db.create_partner(name, slug)
    return JSONResponse(p, status_code=201)


@app.get("/partner/{slug}", response_class=HTMLResponse)
def partner_detail(request: Request, slug: str) -> HTMLResponse:
    partner = db.get_partner_by_slug(slug)
    if not partner:
        raise HTTPException(404, "Partner not found")
    pid = partner["id"]
    topics = db.list_topics(pid)
    for t in topics:
        t["note_count"] = len(db.list_topic_notes(t["id"]))
    jira_config = db.get_jira_config(pid)
    if jira_config:
        jira_config.pop("jira_token", None)
    return templates.TemplateResponse(request, "partner.html", {
        "partner": partner,
        "stats": db.partner_stats(pid),
        "jira_config": jira_config,
        "releases": db.list_releases(pid),
        "operators": db.list_operators(pid),
        "domains": db.list_domains(pid),
        "tickets": db.list_tickets(pid),
        "topics": topics,
        "knowledge": db.list_knowledge(pid),
        "activity": db.list_activity(limit=20, partner_id=pid),
        "auth_sources": db.list_auth_sources(pid),
        "doc_sources": db.list_doc_sources(pid),
        "learned_stats": db.learned_docs_stats_by_source(pid),
        "queue_counts": db.count_learned_docs_by_status(pid),
        "now": date.today().isoformat(),
        "release_operators": db.list_release_operators(pid),
        "skill_exists": (_output_dir() / f"{partner['slug']}-rds-expert").is_dir(),
        "skill_outdated": (
            bool(partner.get("skill_generated_at"))
            and (db.data_last_modified(pid) or "") > (partner.get("skill_generated_at") or "")
        ),
    })


@app.get("/partner/{slug}/topics/{tid}", response_class=HTMLResponse)
def topic_standalone(request: Request, slug: str, tid: str) -> HTMLResponse:
    partner = db.get_partner_by_slug(slug)
    if not partner:
        raise HTTPException(404, "Partner not found")
    topic = db.get_topic(tid)
    if not topic or topic["partner_id"] != partner["id"]:
        raise HTTPException(404, "Topic not found")
    return templates.TemplateResponse(request, "topic.html", {
        "partner": partner,
        "topic": topic,
    })


@app.websocket("/ws/terminal/{pid}")
async def terminal_ws(websocket: WebSocket, pid: str):
    partner = db.get_partner(pid)
    if not partner:
        await websocket.close(code=4004, reason="Partner not found")
        return
    skill_dir = _output_dir() / f"{partner['slug']}-rds-expert"
    if not skill_dir.is_dir():
        await websocket.accept()
        await websocket.send_text("Skill not generated yet. Click Generate first.\r\n")
        await websocket.close()
        return
    await websocket.accept()
    await terminal_handler(websocket, cwd=str(skill_dir))


@app.delete("/api/partners/{pid}")
def delete_partner(pid: str) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    db.delete_partner(pid)
    return JSONResponse({"ok": True})


# -- Jira Config --

@app.post("/api/partners/{pid}/jira-config")
def save_jira_config(
    pid: str,
    jira_mode: str = Form("mcp"),
    cloud_id: str = Form(""),
    jira_url: str = Form(""),
    jira_email: str = Form(""),
    jira_token: str = Form(""),
    project_key: str = Form(""),
    version_prefix: str = Form(""),
) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    if not jira_token:
        existing = db.get_jira_config(pid)
        jira_token = existing["jira_token"] if existing else ""
    cfg = db.set_jira_config(pid, jira_url, jira_email, jira_token, project_key, version_prefix,
                             jira_mode=jira_mode, cloud_id=cloud_id)
    cfg.pop("jira_token", None)
    return JSONResponse(cfg)


# -- Auth Sources --

@app.get("/api/partners/{pid}/auth-sources")
def list_auth_sources(pid: str) -> JSONResponse:
    return JSONResponse(db.list_auth_sources(pid))


@app.post("/api/partners/{pid}/auth-sources")
def create_auth_source(pid: str, domain_pattern: str = Form(...),
                       auth_type: str = Form("cookie"), auth_value: str = Form(""),
                       label: str = Form(""), expires_at: str = Form("")) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    a = db.create_auth_source(pid, domain_pattern, auth_type, auth_value, label,
                              expires_at or None)
    return JSONResponse(a, status_code=201)


@app.put("/api/auth-sources/{aid}")
def update_auth_source(aid: str, domain_pattern: str = Form(None),
                       auth_type: str = Form(None), auth_value: str = Form(None),
                       label: str = Form(None), expires_at: str = Form(None)) -> JSONResponse:
    fields = {k: v for k, v in {"domain_pattern": domain_pattern, "auth_type": auth_type,
              "auth_value": auth_value, "label": label,
              "expires_at": expires_at}.items() if v is not None}
    db.update_auth_source(aid, **fields)
    return JSONResponse({"ok": True})


@app.delete("/api/auth-sources/{aid}")
def delete_auth_source(aid: str) -> JSONResponse:
    db.delete_auth_source(aid)
    return JSONResponse({"ok": True})


# -- Doc Sources --

@app.get("/api/partners/{pid}/doc-sources")
def list_doc_sources(pid: str) -> JSONResponse:
    return JSONResponse(db.list_doc_sources(pid))


@app.post("/api/partners/{pid}/doc-sources")
def create_doc_source(pid: str, name: str = Form(...),
                      source_type: str = Form("sharepoint"),
                      base_url: str = Form(...), path: str = Form(""),
                      auth_source_id: str = Form("")) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    ds = db.create_doc_source(pid, name, source_type, base_url, path,
                              auth_source_id or None)
    return JSONResponse(ds, status_code=201)


@app.put("/api/doc-sources/{dsid}")
def update_doc_source(dsid: str, name: str = Form(None),
                      source_type: str = Form(None),
                      base_url: str = Form(None), path: str = Form(None),
                      auth_source_id: str = Form(None)) -> JSONResponse:
    fields = {k: v for k, v in {"name": name, "source_type": source_type,
              "base_url": base_url, "path": path,
              "auth_source_id": auth_source_id}.items() if v is not None}
    db.update_doc_source(dsid, **fields)
    return JSONResponse({"ok": True})


@app.delete("/api/doc-sources/{dsid}")
def delete_doc_source(dsid: str) -> JSONResponse:
    db.delete_doc_source(dsid)
    return JSONResponse({"ok": True})


@app.post("/api/doc-sources/{dsid}/browse")
def browse_doc_source_route(dsid: str, sub_path: str = Form("")) -> JSONResponse:
    ds = db.get_doc_source(dsid)
    if not ds:
        raise HTTPException(404)
    auth = dict(db._conn.execute("SELECT * FROM auth_sources WHERE id=?",
                (ds["auth_source_id"],)).fetchone()) if ds["auth_source_id"] else None
    browse_path = sub_path if sub_path else ds["path"]
    result = browse_doc_source(ds["source_type"], ds["base_url"], browse_path, auth)
    needs_reauth = any("401" in str(e) for e in result.get("errors", []))
    if needs_reauth:
        return JSONResponse({
            "needs_reauth": True,
            "auth_source_id": ds.get("auth_source_id", ""),
            "errors": result["errors"],
            "files": [], "folders": [],
        })
    db.update_doc_source(dsid, last_browsed_at=_utc_now_iso())
    return JSONResponse(result)


@app.post("/api/doc-sources/{dsid}/learn")
def learn_folder(dsid: str, folder_path: str = Form(""),
                 incremental: str = Form("true")) -> StreamingResponse:
    import json as _json
    ds = db.get_doc_source(dsid)
    if not ds:
        raise HTTPException(404)
    auth = dict(db._conn.execute("SELECT * FROM auth_sources WHERE id=?",
                (ds["auth_source_id"],)).fetchone()) if ds["auth_source_id"] else None
    browse_path = folder_path if folder_path else ds["path"]
    skip_urls = db.learned_urls_for_source(dsid) if incremental == "true" else set()

    def _stream():
        all_files = []
        queue = [browse_path]
        while queue:
            current = queue.pop(0)
            yield _json.dumps({"type": "scanning", "folder": current.split("/")[-1] or current}) + "\n"
            result = browse_doc_source(ds["source_type"], ds["base_url"], current, auth)
            if any("401" in str(e) for e in result.get("errors", [])):
                yield _json.dumps({"type": "auth_error", "auth_source_id": ds.get("auth_source_id", "")}) + "\n"
                return
            for folder in result.get("folders", []):
                queue.append(folder["url"])
            for f in result.get("files", []):
                all_files.append((current, f))

        # Filter out already-learned files in incremental mode
        skipped_existing = 0
        if skip_urls:
            filtered = []
            for folder, f in all_files:
                if f["url"] in skip_urls:
                    skipped_existing += 1
                else:
                    filtered.append((folder, f))
            all_files = filtered

        total = len(all_files)
        yield _json.dumps({"type": "start", "total": total, "skipped_existing": skipped_existing}) + "\n"

        learned = 0
        errors = []
        for i, (folder, f) in enumerate(all_files, 1):
            yield _json.dumps({"type": "progress", "current": i, "total": total, "name": f["name"]}) + "\n"
            try:
                extracted = fetch_and_extract(f["url"], auth_source=auth)
                if extracted.get("error"):
                    errors.append(f"{f['name']}: {extracted['error']}")
                    continue
                if not extracted["content"]:
                    errors.append(f"{f['name']}: no text extracted")
                    continue
                db.create_or_update_learned_doc(
                    partner_id=ds["partner_id"], doc_source_id=dsid,
                    url=f["url"], name=extracted.get("title") or f["name"],
                    folder_path=folder,
                    content_extract=extracted["content"],
                    file_size=int(f.get("size", 0)),
                    modified_at=f.get("modified", ""),
                )
                learned += 1
            except Exception as e:
                errors.append(f"{f['name']}: {e}")

        mode = "incremental" if skip_urls else "full"
        db.log(ds["partner_id"], "docs_learned",
               f"Learned {learned} docs from {browse_path} ({mode}, {skipped_existing} already known)")
        yield _json.dumps({"type": "done", "learned": learned, "skipped": len(errors),
                           "skipped_existing": skipped_existing, "errors": errors}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@app.get("/api/doc-sources/{dsid}/learned")
def get_learned_docs(dsid: str) -> JSONResponse:
    ds = db.get_doc_source(dsid)
    if not ds:
        raise HTTPException(404)
    docs = db.list_learned_docs_by_source(dsid)
    return JSONResponse([{
        "id": d["id"], "name": d["name"], "folder_path": d["folder_path"],
        "file_size": d["file_size"], "learned_at": d["learned_at"], "url": d["url"],
    } for d in docs])


@app.delete("/api/learned-docs/{lid}")
def delete_learned_doc_route(lid: str) -> JSONResponse:
    db.delete_learned_doc(lid)
    return JSONResponse({"ok": True})


@app.put("/api/learned-docs/{lid}/status")
def update_learned_doc_status(lid: str, status: str = Form(...)) -> JSONResponse:
    if status not in ("backlog", "approved", "processed", "ignored"):
        raise HTTPException(400, "Invalid status")
    db.update_learned_doc_status(lid, status)
    return JSONResponse({"ok": True})


@app.post("/api/partners/{pid}/learned-docs/bulk")
def bulk_update_learned_docs(pid: str, ids: str = Form(...),
                             status: str = Form(...)) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    if status not in ("backlog", "approved", "processed", "ignored"):
        raise HTTPException(400, "Invalid status")
    import json as _json
    try:
        id_list = _json.loads(ids)
    except Exception:
        id_list = [i.strip() for i in ids.split(",") if i.strip()]
    count = db.bulk_update_learned_doc_status(id_list, status)
    return JSONResponse({"ok": True, "updated": count})


@app.get("/api/partners/{pid}/learned-docs/queue")
def learned_docs_queue(pid: str, status: str = "backlog") -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    docs = db.list_learned_docs_by_status(pid, status)
    return JSONResponse([{
        "id": d["id"], "name": d["name"], "folder_path": d["folder_path"],
        "file_size": d["file_size"], "learned_at": d["learned_at"], "url": d["url"],
        "modified_at": d.get("modified_at", ""),
        "processing_status": d["processing_status"],
        "content_extract": d["content_extract"][:200] if d.get("content_extract") else "",
    } for d in docs])


@app.post("/api/partners/{pid}/doc-sources/add-with-auth")
def add_doc_source_with_auth(pid: str, url: str = Form(...),
                              name: str = Form("")) -> JSONResponse:
    """Parse SharePoint URL, open browser for SSO, create auth_source + doc_source."""
    if not db.get_partner(pid):
        raise HTTPException(404)
    from tps.auth_capture import parse_sharepoint_url, capture_sharepoint_cookies

    parsed = parse_sharepoint_url(url)
    display_name = name or parsed["name"]

    try:
        result = capture_sharepoint_cookies(url)
    except RuntimeError as e:
        raise HTTPException(408, str(e))

    auth = db.create_auth_source(
        pid, domain_pattern=parsed["domain"], auth_type="cookie",
        auth_value=result["cookies"], label=f"{display_name} SSO",
        expires_at=result["expires_at"],
    )
    ds = db.create_doc_source(
        pid, name=display_name, source_type="sharepoint",
        base_url=parsed["base_url"], path=parsed["path"],
        auth_source_id=auth["id"],
    )
    return JSONResponse(ds, status_code=201)


@app.post("/api/auth-sources/{aid}/recapture")
def recapture_auth(aid: str) -> JSONResponse:
    """Re-open browser for SSO login, update existing auth_source cookies."""
    row = db._conn.execute("SELECT * FROM auth_sources WHERE id=?", (aid,)).fetchone()
    if not row:
        raise HTTPException(404)
    ds = db._conn.execute(
        "SELECT * FROM doc_sources WHERE auth_source_id=?", (aid,)
    ).fetchone()
    if not ds:
        raise HTTPException(400, "No doc source linked to this auth source")

    url = f"{ds['base_url']}/{ds['path']}".rstrip("/")
    from tps.auth_capture import capture_sharepoint_cookies
    try:
        result = capture_sharepoint_cookies(url)
    except RuntimeError as e:
        raise HTTPException(408, str(e))

    db.update_auth_source(aid, auth_value=result["cookies"],
                          expires_at=result["expires_at"])
    return JSONResponse({"ok": True, "expires_at": result["expires_at"]})


# -- Jira Import --

@app.post("/api/partners/{pid}/import")
def jira_import(pid: str) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    try:
        result = import_from_jira(db, pid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Jira request failed: {e}")
    return JSONResponse(result)


@app.get("/api/partners/{pid}/suggest-domains")
def get_domain_suggestions(pid: str) -> JSONResponse:
    tickets = db.list_tickets(pid)
    suggestions = suggest_domains(tickets)
    return JSONResponse({"suggestions": suggestions})


# -- Releases --

@app.post("/api/partners/{pid}/releases")
def create_release(
    pid: str,
    release_name: str = Form(...),
    ocp_version: str = Form(""),
    partner_build: str = Form(""),
    ga_date: str = Form(""),
    eol_date: str = Form(""),
    doc_url: str = Form(""),
    release_status: str = Form("ga"),
) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    r = db.create_release(pid, release_name, ocp_version, partner_build,
                          ga_date=ga_date, eol_date=eol_date, doc_url=doc_url,
                          release_status=release_status)
    return JSONResponse(r, status_code=201)


@app.put("/api/releases/{rid}")
def update_release(rid: str, release_name: str = Form(None),
                   ocp_version: str = Form(None), partner_build: str = Form(None),
                   ga_date: str = Form(None), eol_date: str = Form(None),
                   doc_url: str = Form(None), release_status: str = Form(None)) -> JSONResponse:
    fields = {k: v for k, v in {"release_name": release_name, "ocp_version": ocp_version,
              "partner_build": partner_build, "ga_date": ga_date, "eol_date": eol_date,
              "doc_url": doc_url, "release_status": release_status}.items() if v is not None}
    db.update_release(rid, **fields)
    return JSONResponse({"ok": True})


@app.delete("/api/releases/{rid}")
def delete_release(rid: str) -> JSONResponse:
    db.delete_release(rid)
    return JSONResponse({"ok": True})


@app.get("/api/ocp-versions")
def get_ocp_versions() -> JSONResponse:
    return JSONResponse(fetch_ocp_releases())


# -- Operators --

@app.post("/api/partners/{pid}/operators")
def create_operator(
    pid: str,
    operator_name: str = Form(...),
    channel: str = Form(""),
    current_version: str = Form(""),
    source: str = Form("redhat-operators"),
    operator_status: str = Form("deployed"),
    doc_url: str = Form(""),
    notes: str = Form(""),
) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    o = db.create_operator(pid, operator_name, channel, current_version,
                           source=source, operator_status=operator_status,
                           doc_url=doc_url, notes=notes)
    return JSONResponse(o, status_code=201)


@app.put("/api/operators/{oid}")
def update_operator(oid: str, operator_name: str = Form(None),
                    channel: str = Form(None), current_version: str = Form(None),
                    source: str = Form(None), operator_status: str = Form(None),
                    doc_url: str = Form(None), notes: str = Form(None)) -> JSONResponse:
    fields = {k: v for k, v in {"operator_name": operator_name, "channel": channel,
              "current_version": current_version, "source": source,
              "operator_status": operator_status, "doc_url": doc_url,
              "notes": notes}.items() if v is not None}
    db.update_operator(oid, **fields)
    return JSONResponse({"ok": True})


@app.delete("/api/operators/{oid}")
def delete_operator(oid: str) -> JSONResponse:
    db.delete_operator(oid)
    return JSONResponse({"ok": True})


@app.get("/api/operators/{oid}/pins")
def get_operator_pins(oid: str) -> JSONResponse:
    return JSONResponse(db.get_operator_pins(oid))


@app.post("/api/operators/{oid}/pins")
def pin_operator_version(oid: str, release_id: str = Form(...),
                         pinned_version: str = Form("")) -> JSONResponse:
    pin = db.pin_operator_version(release_id, oid, pinned_version)
    return JSONResponse(pin)


@app.delete("/api/operator-pins/{pin_id}")
def delete_operator_pin(pin_id: str) -> JSONResponse:
    db.delete_operator_pin(pin_id)
    return JSONResponse({"ok": True})


# -- Domains --

@app.post("/api/partners/{pid}/domains")
def create_domain(pid: str, name: str = Form(...), description: str = Form("")) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    d = db.create_domain(pid, name, description)
    return JSONResponse(d, status_code=201)


@app.put("/api/domains/{did}")
def update_domain(did: str, name: str = Form(None), description: str = Form(None)) -> JSONResponse:
    fields = {k: v for k, v in {"name": name, "description": description}.items() if v is not None}
    db.update_domain(did, **fields)
    return JSONResponse({"ok": True})


@app.delete("/api/domains/{did}")
def delete_domain(did: str) -> JSONResponse:
    db.delete_domain(did)
    return JSONResponse({"ok": True})


# -- Tickets --

@app.post("/api/partners/{pid}/tickets")
def create_ticket(
    pid: str,
    ecops_key: str = Form(...),
    summary: str = Form(""),
    resolution: str = Form(""),
    release_id: str = Form(""),
    domain_id: str = Form(""),
) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    t = db.create_ticket(
        pid, ecops_key, summary, resolution,
        release_id=release_id or None,
        domain_id=domain_id or None,
    )
    return JSONResponse(t, status_code=201)


@app.put("/api/tickets/{tid}")
def update_ticket(tid: str, domain_id: str = Form(None),
                  release_id: str = Form(None), summary: str = Form(None),
                  resolution: str = Form(None)) -> JSONResponse:
    fields = {k: v for k, v in {"domain_id": domain_id, "release_id": release_id,
              "summary": summary, "resolution": resolution}.items() if v is not None}
    db.update_ticket(tid, **fields)
    return JSONResponse({"ok": True})


@app.delete("/api/tickets/{tid}")
def delete_ticket(tid: str) -> JSONResponse:
    db.delete_ticket(tid)
    return JSONResponse({"ok": True})


# -- Topics --

@app.get("/api/partners/{pid}/topics")
def list_topics_api(pid: str, status: str | None = None) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    topics = db.list_topics(pid, status or None)
    for t in topics:
        t["note_count"] = len(db.list_topic_notes(t["id"]))
    return JSONResponse(topics)


@app.post("/api/partners/{pid}/topics")
def create_topic(pid: str, title: str = Form(...), description: str = Form(""),
                 status: str = Form("open")) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    t = db.create_topic(pid, title, description, status)
    return JSONResponse(t, status_code=201)


@app.get("/api/topics/{tid}")
def get_topic(tid: str) -> JSONResponse:
    topic = db.get_topic(tid)
    if not topic:
        raise HTTPException(404)
    topic["notes"] = db.list_topic_notes(tid)
    topic["interactions"] = db.list_topic_interactions(tid)
    topic["sources"] = db.list_topic_sources(tid)
    topic["results"] = db.list_topic_results(tid)
    topic["tickets"] = db.list_topic_tickets(tid)
    topic["workspace"] = str(ensure_topic_workspace(tid))
    jira_cfg = db.get_jira_config(topic["partner_id"])
    topic["jira_configured"] = jira_cfg is not None
    topic["jira_mode"] = jira_cfg.get("jira_mode", "mcp") if jira_cfg else None
    return JSONResponse(topic)


@app.put("/api/topics/{tid}")
def update_topic(tid: str, title: str = Form(None), status: str = Form(None),
                 description: str = Form(None)) -> JSONResponse:
    fields = {k: v for k, v in {"title": title, "status": status,
              "description": description}.items() if v is not None}
    db.update_topic(tid, **fields)
    return JSONResponse({"ok": True})


@app.delete("/api/topics/{tid}")
def delete_topic(tid: str) -> JSONResponse:
    db.delete_topic(tid)
    return JSONResponse({"ok": True})


# -- Topic Notes --

@app.post("/api/topics/{tid}/notes")
def create_topic_note(tid: str, content: str = Form(...),
                      note_type: str = Form("research")) -> JSONResponse:
    if not db.get_topic(tid):
        raise HTTPException(404)
    n = db.create_topic_note(tid, content, note_type)
    return JSONResponse(n, status_code=201)


@app.delete("/api/topic-notes/{nid}")
def delete_topic_note(nid: str) -> JSONResponse:
    db.delete_topic_note(nid)
    return JSONResponse({"ok": True})


# -- Topic Sources --

def _auth_for_url(partner_id: str, url: str) -> dict | None:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    return db.get_auth_for_domain(partner_id, domain)


@app.post("/api/topics/{tid}/sources")
def create_topic_source(tid: str, url: str = Form(...), title: str = Form(""),
                        source_tier: int = Form(0),
                        content_extract: str = Form(""),
                        auto_fetch: str = Form("true")) -> JSONResponse:
    topic = db.get_topic(tid)
    if not topic:
        raise HTTPException(404)
    if auto_fetch == "true" and not content_extract:
        auth = _auth_for_url(topic["partner_id"], url)
        result = fetch_and_extract(url, auth_source=auth)
        if not title and result["title"]:
            title = result["title"]
        if source_tier == 0:
            source_tier = result["tier"]
        content_extract = result["content"]
    if source_tier == 0:
        source_tier = 4
    s = db.create_topic_source(tid, url, title, source_tier, content_extract)
    return JSONResponse(s, status_code=201)


@app.post("/api/topic-sources/{sid}/fetch")
def refetch_topic_source(sid: str) -> JSONResponse:
    source = db._conn.execute("SELECT * FROM topic_sources WHERE id=?", (sid,)).fetchone()
    if not source:
        raise HTTPException(404)
    topic = db.get_topic(source["topic_id"])
    auth = _auth_for_url(topic["partner_id"], source["url"]) if topic else None
    result = fetch_and_extract(source["url"], auth_source=auth)
    if result["error"]:
        raise HTTPException(400, f"Fetch failed: {result['error']}")
    updates = {"content_extract": result["content"], "source_tier": result["tier"]}
    if result["title"] and not source["title"]:
        updates["title"] = result["title"]
    db.update_topic_source(sid, **updates)
    return JSONResponse({"ok": True, "title": result["title"], "tier": result["tier"],
                         "content_length": len(result["content"])})


@app.delete("/api/topic-sources/{sid}")
def delete_topic_source(sid: str) -> JSONResponse:
    db.delete_topic_source(sid)
    return JSONResponse({"ok": True})


# -- Topic Results --

@app.post("/api/topics/{tid}/results")
def create_topic_result(tid: str, title: str = Form(...),
                        description: str = Form(""),
                        result_type: str = Form("document"),
                        file_path: str = Form(""),
                        url: str = Form("")) -> JSONResponse:
    if not db.get_topic(tid):
        raise HTTPException(404)
    ensure_topic_workspace(tid)
    r = db.create_topic_result(tid, title, description, result_type, file_path, url)
    return JSONResponse(r, status_code=201)


@app.delete("/api/topic-results/{rid}")
def delete_topic_result(rid: str) -> JSONResponse:
    db.delete_topic_result(rid)
    return JSONResponse({"ok": True})


# -- Workspace file serving --

@app.get("/workspace/{path:path}")
def serve_workspace_file(path: str):
    full = (_WORKSPACE / path).resolve()
    if not full.is_relative_to(_WORKSPACE.resolve()):
        raise HTTPException(403, "Access denied")
    if not full.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(full)


# -- Topic Tickets --

@app.post("/api/topics/{tid}/tickets")
def link_topic_ticket(tid: str, ticket_key: str = Form(...),
                      ticket_url: str = Form(""),
                      relationship: str = Form("related"),
                      summary: str = Form(""),
                      jira_status: str = Form("")) -> JSONResponse:
    if not db.get_topic(tid):
        raise HTTPException(404)
    lt = db.link_topic_ticket(tid, ticket_key, ticket_url, relationship,
                              summary=summary, jira_status=jira_status)
    return JSONResponse(lt, status_code=201)


@app.delete("/api/topic-tickets/{ltid}")
def unlink_topic_ticket(ltid: str) -> JSONResponse:
    db.unlink_topic_ticket(ltid)
    return JSONResponse({"ok": True})


# -- Jira Live --

@app.post("/api/partners/{pid}/jira-search")
def jira_search_route(pid: str, query: str = Form(...)) -> JSONResponse:
    try:
        results = jira_search(db, pid, query)
        return JSONResponse(results)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/partners/{pid}/jira/issue/{key}")
def jira_issue_route(pid: str, key: str) -> JSONResponse:
    try:
        issue = jira_get_issue(db, pid, key)
        return JSONResponse(issue)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/partners/{pid}/jira-create")
def jira_create_route(pid: str, summary: str = Form(...),
                      description: str = Form(""),
                      issue_type: str = Form("Task")) -> JSONResponse:
    try:
        result = jira_create_issue(db, pid, summary, description, issue_type)
        return JSONResponse(result, status_code=201)
    except ValueError as e:
        raise HTTPException(400, str(e))


# -- Knowledge --

@app.get("/api/partners/{pid}/knowledge")
def list_knowledge_api(pid: str, category: str | None = None,
                       status: str | None = None) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    return JSONResponse(db.list_knowledge(pid, category or None, status or None))


@app.post("/api/partners/{pid}/knowledge")
def create_knowledge(
    pid: str,
    category: str = Form(...),
    fact: str = Form(...),
    detail: str = Form(""),
    source_url: str = Form(""),
    source_tier: int = Form(4),
    topic_id: str = Form(""),
    status: str = Form("confirmed"),
) -> JSONResponse:
    if not db.get_partner(pid):
        raise HTTPException(404)
    k = db.create_knowledge(pid, category, fact, detail, source_url, source_tier,
                            topic_id=topic_id or None, status=status)
    return JSONResponse(k, status_code=201)


@app.put("/api/knowledge/{kid}")
def update_knowledge(kid: str, category: str = Form(None), fact: str = Form(None),
                     detail: str = Form(None), source_url: str = Form(None),
                     source_tier: int = Form(None), status: str = Form(None)) -> JSONResponse:
    fields = {k: v for k, v in {"category": category, "fact": fact, "detail": detail,
              "source_url": source_url, "source_tier": source_tier,
              "status": status}.items() if v is not None}
    db.update_knowledge(kid, **fields)
    return JSONResponse({"ok": True})


@app.delete("/api/knowledge/{kid}")
def delete_knowledge(kid: str) -> JSONResponse:
    db.delete_knowledge(kid)
    return JSONResponse({"ok": True})


# -- Skill Generation --

@app.post("/api/partners/{pid}/generate")
def generate(pid: str) -> JSONResponse:
    partner = db.get_partner(pid)
    if not partner:
        raise HTTPException(404)
    try:
        out_path = generate_skill(db, pid, output_dir=_output_dir())
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {e}")
    install_cmd = f'export OPENAI_TPS_CONTEXT={out_path}'
    return JSONResponse({"path": str(out_path), "install_cmd": install_cmd})


# -- App Settings --

@app.get("/api/settings/output-path")
def get_output_path() -> JSONResponse:
    custom = db.get_setting("output_path")
    return JSONResponse({
        "path": custom or str(_DEFAULT_OUTPUT),
        "is_default": custom is None,
    })


@app.put("/api/settings/output-path")
async def set_output_path(request: Request) -> JSONResponse:
    data = await request.json()
    path_str = data.get("path", "").strip()
    if not path_str:
        raise HTTPException(400, "Path required")
    p = Path(path_str).resolve()
    p.mkdir(parents=True, exist_ok=True)
    db.set_setting("output_path", str(p))
    db.log(None, "output_path_changed", f"Output path set to {p}")
    return JSONResponse({"path": str(p)})


@app.get("/api/browse-dirs")
def browse_dirs(path: str = "") -> JSONResponse:
    target = Path(path).resolve() if path else Path.home()
    # ponytail: never 400 — walk up until we find a dir that exists, fall back to home
    while not target.is_dir():
        if target.parent == target:
            target = Path.home()
            break
        target = target.parent
    parent = str(target.parent) if target.parent != target else None
    dirs = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: e.name.lower()):
            if entry.is_dir() and not entry.name.startswith("."):
                dirs.append({"name": entry.name, "path": str(entry)})
    except PermissionError:
        pass
    return JSONResponse({"current": str(target), "parent": parent, "dirs": dirs})


# -- Backup & Restore --

@app.get("/api/backups")
def api_list_backups() -> JSONResponse:
    return JSONResponse({"backups": list_backups(_BACKUP_DIR)})


@app.post("/api/backups")
def api_create_backup() -> JSONResponse:
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = _BACKUP_DIR / f"manual_{stamp}.zip"
    ok, msg = create_backup(db._conn, _WORKSPACE, dest)
    if not ok:
        raise HTTPException(500, msg)
    info = {"filename": dest.name, "size_mb": round(dest.stat().st_size / (1024 * 1024), 2)}
    return JSONResponse({"ok": True, "message": msg, **info})


@app.get("/api/backups/{filename}")
def api_download_backup(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or not filename.endswith(".zip"):
        raise HTTPException(400, "Invalid filename")
    path = _BACKUP_DIR / filename
    if not path.is_file():
        raise HTTPException(404, "Backup not found")
    return FileResponse(path, media_type="application/zip", filename=filename)


@app.post("/api/restore")
async def api_restore(file: UploadFile) -> JSONResponse:
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "Upload a .zip backup file")
    tmp = _BACKUP_DIR / f"_upload_{file.filename}"
    try:
        with open(tmp, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
        ok, msg = restore_backup(tmp, db, _WORKSPACE, _BACKUP_DIR)
        if not ok:
            raise HTTPException(500, msg)
        return JSONResponse({"ok": True, "message": msg})
    finally:
        tmp.unlink(missing_ok=True)


# -- Architect session hooks --
# Legacy-compatible topic endpoints; the embedded OpenAI adapter does not need
# provider lifecycle hooks.

import logging as _logging
_hook_log = _logging.getLogger("tps.hooks")


def _partner_from_cwd(cwd: str) -> dict | None:
    """Derive partner from the skill directory path (output/<slug>-rds-expert/)."""
    m = re.search(r"/([a-z0-9_-]+)-rds-expert/?$", cwd)
    if not m:
        return None
    return db.get_partner_by_slug(m.group(1))


@app.get("/api/partners/{pid}/active-topic")
def get_active_topic(pid: str) -> JSONResponse:
    """Return the most recent active topic for this partner's terminal sessions."""
    row = db._conn.execute(
        "SELECT ts.active_topic_id, t.title, t.status FROM topic_sessions ts "
        "JOIN topics t ON ts.active_topic_id = t.id "
        "WHERE ts.partner_id=? AND ts.ended_at IS NULL AND ts.active_topic_id IS NOT NULL "
        "ORDER BY ts.started_at DESC LIMIT 1",
        (pid,),
    ).fetchone()
    if not row:
        return JSONResponse({"active": False})
    return JSONResponse({
        "active": True,
        "topic_id": row["active_topic_id"],
        "title": row["title"],
        "status": row["status"],
    })


def _topic_list_str(candidates: list[dict]) -> str:
    if not candidates:
        return "(no existing open topics)"
    return "; ".join(f'"{c["title"]}" (id={c["id"]})' for c in candidates)


def _confirm_context(route: dict, prompt: str) -> str:
    """Context telling the Architect to verify topic choice with the user first."""
    reason = route.get("reason", "no_active_topic")
    topics = _topic_list_str(route.get("candidates", []))
    proposed = route.get("title") or _derive_title(prompt)
    if reason == "no_active_topic":
        return (
            "⛔ TPS HARD GATE: no active topic for this session. Do NOT create, "
            "assume, or do any work. Your reply MUST be to ask the user which topic "
            f"to work on — nothing else. Open topics: {topics}. "
            f"If none fit, offer to create \"{proposed}\". "
            "The user can just say e.g. \"work on <topic>\" or "
            "\"create a new topic called <name>\"."
        )
    if reason == "switch_no_match":
        return (
            f"TPS: no existing topic matches \"{proposed}\". Do NOT create it yet. "
            f"Ask the user to confirm creating \"{proposed}\", or pick an "
            f"existing one: {topics}."
        )
    if reason == "create_needs_name":
        return (
            "TPS: you asked to create a new topic but gave no name. "
            "Ask the user for a title, then say "
            "\"create a new topic called <name>\"."
        )
    return (
        f"TPS: topic choice needs confirmation. Open topics: {topics}. "
        "Ask the user which to use before proceeding."
    )


@app.post("/hooks/session-start")
async def hook_session_start(request: Request) -> JSONResponse:
    try:
        data = await request.json()
        session_id = data.get("session_id", "")
        cwd = data.get("cwd", "")
        if not session_id:
            return JSONResponse({"hookSpecificOutput": {"hookEventName": "SessionStart"}})

        partner = _partner_from_cwd(cwd)
        if not partner:
            return JSONResponse({"hookSpecificOutput": {"hookEventName": "SessionStart"}})

        session = db.create_topic_session(partner["id"], session_id)
        context = (
            "You are in the TPS (Telco Partner Skills) framework. "
            "Your interactions are automatically logged to topics — "
            "you do not need to manually log prompts or responses via curl. "
            "Continue posting curated notes (findings, decisions, questions) "
            "via the topic notes API when you discover something worth preserving."
        )
        context += (
            "\n\nTopic policy: TPS never creates or switches topics on its own. "
            "It logs to the active topic, or asks you. To choose, say "
            "\"work on <topic>\" or \"create a new topic called <name>\"."
        )
        topic = db.get_topic(session["active_topic_id"]) if session.get("active_topic_id") else None
        if topic:
            context += f"\n\nActive topic: \"{topic['title']}\" (id={topic['id']}, status={topic['status']})"
            latest = db.get_latest_interaction(session["id"])
            if latest and latest.get("response"):
                context += f"\nLast interaction: {latest['response'][:200]}..."
            context += "\nConfirm with the user they want to continue this topic before starting work."
        else:
            # No active topic — present open topics and ask which one.
            open_topics = _recent_open_topics(db, partner["id"], None)
            context += (
                f"\n\n⛔ NO ACTIVE TOPIC. This is a hard gate: your FIRST reply this "
                "session MUST be to ask the user which topic to work on. Do NOT answer "
                "their message, run tools, or do any work until they pick a topic or ask "
                f"to create one. Open topics: {_topic_list_str(open_topics)}. "
                "Reply now with the list and the question — nothing else."
            )

        return JSONResponse({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        })
    except Exception:
        _hook_log.exception("session-start hook error")
        return JSONResponse({})


@app.post("/hooks/prompt-submit")
async def hook_prompt_submit(request: Request) -> JSONResponse:
    try:
        data = await request.json()
        session_id = data.get("session_id", "")
        prompt = data.get("prompt", "")
        cwd = data.get("cwd", "")
        if not session_id or not prompt:
            return JSONResponse({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}})

        partner = _partner_from_cwd(cwd)
        if not partner:
            return JSONResponse({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}})

        session = db.create_topic_session(partner["id"], session_id)
        route = route_prompt(db, partner["id"], session, prompt)

        if route["decision"] == "confirm":
            # TPS will not create or switch topics on its own. Ask the user,
            # and (if a topic is active) keep logging there so nothing is lost.
            context = _confirm_context(route, prompt)
            active_id = session.get("active_topic_id")
            if active_id:
                db.create_topic_interaction(
                    session["id"], active_id, prompt,
                    routed_by="confirm_pending",
                    confidence=route.get("confidence"),
                )
            return JSONResponse({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            })

        # continue | use_existing | create — all authorised (active topic or an
        # explicit user command).
        if route["decision"] == "create":
            topic = db.create_topic(partner["id"], route["title"] or "Untitled topic")
            route["topic_id"] = topic["id"]
        else:
            topic = db.get_topic(route["topic_id"])
            if not topic:
                # Active/target topic vanished — fall back to asking.
                context = _confirm_context(
                    {"reason": "no_active_topic", "title": _derive_title(prompt),
                     "candidates": []}, prompt)
                return JSONResponse({"hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit", "additionalContext": context}})

        db.update_topic_session(session["id"], active_topic_id=route["topic_id"])
        db.create_topic_interaction(
            session["id"], route["topic_id"], prompt,
            routed_by=route["routed_by"],
            confidence=route.get("confidence"),
        )

        context = f"TPS: topic=\"{topic['title']}\" (id={topic['id']})"
        if route["decision"] == "create":
            context += " [new topic created on your command]"
        elif route["decision"] == "use_existing":
            context += " [switched to this topic on your command]"

        return JSONResponse({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }
        })
    except Exception:
        _hook_log.exception("prompt-submit hook error")
        return JSONResponse({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}})


@app.post("/hooks/stop")
async def hook_stop(request: Request) -> JSONResponse:
    try:
        data = await request.json()
        session_id = data.get("session_id", "")
        response_text = data.get("last_assistant_message", "")
        if not session_id:
            return JSONResponse({})

        session = db.get_topic_session_by_claude_id(session_id)
        if not session:
            return JSONResponse({})

        latest = db.get_latest_interaction(session["id"])
        if latest and not latest.get("completed_at"):
            db.complete_topic_interaction(latest["id"], response_text or "")
    except Exception:
        _hook_log.exception("stop hook error")
    return JSONResponse({})


@app.post("/hooks/session-end")
async def hook_session_end(request: Request) -> JSONResponse:
    try:
        data = await request.json()
        session_id = data.get("session_id", "")
        if not session_id:
            return JSONResponse({})
        session = db.get_topic_session_by_claude_id(session_id)
        if session:
            db.update_topic_session(session["id"], ended_at=_utc_now_iso())
    except Exception:
        _hook_log.exception("session-end hook error")
    return JSONResponse({})


# -- Static assets --
if _STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
