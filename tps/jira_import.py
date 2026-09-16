from __future__ import annotations

import json
import re

import httpx

from tps.db import Database


def import_from_jira(db: Database, partner_id: str) -> dict:
    config = db.get_jira_config(partner_id)
    if not config:
        raise ValueError("Jira not configured for this partner")

    jira_url = config["jira_url"].rstrip("/")
    auth = (config["jira_email"], config["jira_token"])
    project_key = config["project_key"]
    version_prefix = config["version_prefix"]

    jql = (
        f'project = {project_key} AND affectedVersion in '
        f'versionMatch("{version_prefix}*") ORDER BY key'
    )

    issues = _fetch_all_issues(jira_url, auth, jql)

    imported = 0
    updated = 0
    skipped = 0
    releases_created = []

    existing_releases = {r["release_name"]: r for r in db.list_releases(partner_id)}

    _res_map = {"Done-Errata": "Support Exception", "Not a Bug": "Non-Impacting"}

    for issue in issues:
        ecops_key = issue["key"]
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        resolution = _res_map.get(
            (fields.get("resolution") or {}).get("name", ""),
            (fields.get("resolution") or {}).get("name", "")
        )
        labels = ",".join(fields.get("labels", []))

        versions = fields.get("versions", [])
        partner_versions = [
            v["name"] for v in versions
            if v.get("name", "").startswith(version_prefix)
        ]

        release_id = None
        if partner_versions:
            rel_name = partner_versions[0].replace(version_prefix + "-", "")
            if rel_name in existing_releases:
                release_id = existing_releases[rel_name]["id"]
            else:
                r = db.create_release(partner_id, rel_name)
                existing_releases[rel_name] = r
                release_id = r["id"]
                releases_created.append(rel_name)

        existing = db.get_ticket_by_key(partner_id, ecops_key)
        if existing:
            changed = (
                existing.get("summary") != summary
                or existing.get("resolution") != resolution
                or existing.get("labels") != labels
            )
            if changed:
                db.update_ticket(existing["id"], summary=summary,
                                 resolution=resolution, labels=labels)
                updated += 1
            else:
                skipped += 1
        else:
            db.create_ticket(
                partner_id=partner_id,
                ecops_key=ecops_key,
                summary=summary,
                resolution=resolution,
                labels=labels,
                raw_json=json.dumps(issue),
                release_id=release_id,
                domain_id=None,
            )
            imported += 1

    detail = f"Synced: {imported} new, {updated} updated, {skipped} unchanged"
    if releases_created:
        detail += f", created releases: {', '.join(releases_created)}"
    db.log(partner_id, "jira_import", detail)

    return {"imported": imported, "updated": updated, "skipped": skipped,
            "releases_created": releases_created}


def suggest_domains(tickets: list[dict]) -> list[str]:
    keywords = [
        "ClusterLogging", "APIServer", "MachineConfig", "PerformanceProfile",
        "Tuned", "Composable", "Monitoring", "OperatorGroup", "ODF",
        "ImageRegistry", "CSISnapshot", "kubeletconfig",
    ]
    found = set()
    for t in tickets:
        summary = t.get("summary", "")
        for kw in keywords:
            if kw.lower() in summary.lower():
                found.add(kw)
    return sorted(found)


def _fetch_all_issues(jira_url: str, auth: tuple[str, str], jql: str) -> list[dict]:
    all_issues: list[dict] = []
    start_at = 0
    max_results = 100

    while True:
        resp = httpx.get(
            f"{jira_url}/rest/api/3/search",
            params={
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
                "fields": "summary,status,versions,resolution,labels,assignee",
            },
            auth=auth,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)

        if start_at + len(issues) >= data.get("total", 0):
            break
        start_at += len(issues)

    return all_issues


def _get_config(db: Database, partner_id: str) -> dict:
    config = db.get_jira_config(partner_id)
    if not config:
        raise ValueError("Jira not configured for this partner")
    if config.get("jira_mode", "mcp") == "mcp":
        raise ValueError("Jira is configured for MCP mode — use the OpenAI Architect for live Jira access")
    return config


def _adf_to_text(node: dict | list | None) -> str:
    if not node:
        return ""
    if isinstance(node, list):
        return "".join(_adf_to_text(n) for n in node)
    if isinstance(node, str):
        return node
    text = node.get("text", "")
    children = node.get("content", [])
    return text + _adf_to_text(children)


def jira_search(db: Database, partner_id: str, query: str, max_results: int = 20) -> list[dict]:
    config = _get_config(db, partner_id)
    jira_url = config["jira_url"].rstrip("/")
    auth = (config["jira_email"], config["jira_token"])
    project_key = config["project_key"]

    if any(op in query for op in ("=", "~", "ORDER BY")):
        jql = query
    else:
        projects = [p.strip() for p in project_key.split(",")]
        if len(projects) > 1:
            proj_clause = f"project in ({','.join(projects)})"
        else:
            proj_clause = f"project = {projects[0]}"
        jql = f'{proj_clause} AND text ~ "{query}" ORDER BY updated DESC'

    resp = httpx.get(
        f"{jira_url}/rest/api/3/search",
        params={"jql": jql, "maxResults": max_results,
                "fields": "summary,status,assignee,priority,updated"},
        auth=auth, timeout=30,
    )
    resp.raise_for_status()

    results = []
    for issue in resp.json().get("issues", []):
        f = issue.get("fields", {})
        results.append({
            "key": issue["key"],
            "summary": f.get("summary", ""),
            "status": f.get("status", {}).get("name", ""),
            "assignee": (f.get("assignee") or {}).get("displayName", ""),
            "priority": (f.get("priority") or {}).get("name", ""),
            "updated": f.get("updated", "")[:10],
            "url": f"{jira_url}/browse/{issue['key']}",
        })

    db.log(partner_id, "jira_search", f"Query: {query}, {len(results)} results")
    return results


def jira_get_issue(db: Database, partner_id: str, issue_key: str) -> dict:
    config = _get_config(db, partner_id)
    jira_url = config["jira_url"].rstrip("/")
    auth = (config["jira_email"], config["jira_token"])

    resp = httpx.get(
        f"{jira_url}/rest/api/3/issue/{issue_key}",
        params={"fields": "summary,status,assignee,reporter,priority,description,comment,updated,resolution,labels"},
        auth=auth, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    f = data.get("fields", {})

    comments_raw = (f.get("comment") or {}).get("comments", [])[-10:]
    comments = [{
        "author": (c.get("author") or {}).get("displayName", ""),
        "created": c.get("created", "")[:16],
        "body": _adf_to_text(c.get("body")),
    } for c in comments_raw]

    result = {
        "key": data["key"],
        "summary": f.get("summary", ""),
        "status": (f.get("status") or {}).get("name", ""),
        "assignee": (f.get("assignee") or {}).get("displayName", ""),
        "reporter": (f.get("reporter") or {}).get("displayName", ""),
        "priority": (f.get("priority") or {}).get("name", ""),
        "resolution": (f.get("resolution") or {}).get("name", ""),
        "labels": f.get("labels", []),
        "updated": f.get("updated", "")[:16],
        "description": _adf_to_text(f.get("description")),
        "comments": comments,
        "url": f"{jira_url}/browse/{data['key']}",
    }

    db.log(partner_id, "jira_review", f"Reviewed {issue_key}")
    return result


def jira_create_issue(db: Database, partner_id: str, summary: str,
                      description: str = "", issue_type: str = "Task") -> dict:
    config = _get_config(db, partner_id)
    jira_url = config["jira_url"].rstrip("/")
    auth = (config["jira_email"], config["jira_token"])
    project_key = config["project_key"].split(",")[0].strip()

    desc_adf = {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": description}]}
    ]} if description else {"type": "doc", "version": 1, "content": []}

    payload = {"fields": {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
        "description": desc_adf,
    }}

    resp = httpx.post(
        f"{jira_url}/rest/api/3/issue",
        json=payload, auth=auth, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    key = data["key"]

    db.log(partner_id, "jira_create", f"Created {key}: {summary[:80]}")
    return {"key": key, "url": f"{jira_url}/browse/{key}"}
