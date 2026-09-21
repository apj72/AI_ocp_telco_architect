from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from tps.db import Database

_ROOT = Path(__file__).resolve().parent.parent
_SKILL_BASE = _ROOT / "skill-base"
_DEFAULT_OUTPUT = _ROOT / "output"


def generate_skill(db: Database, partner_id: str,
                   output_dir: Path | None = None) -> Path:
    partner = db.get_partner(partner_id)
    if not partner:
        raise ValueError("Partner not found")

    slug = partner["slug"]
    name = partner["name"]

    tickets = db.list_tickets(partner_id)
    releases = db.list_releases(partner_id)
    domains = db.list_domains(partner_id)
    jira_config = db.get_jira_config(partner_id)
    operators = db.list_operators(partner_id)
    release_operators = db.list_release_operators(partner_id)
    knowledge = db.list_knowledge(partner_id)
    non_negotiables = [{"fact": k["fact"], "detail": k["detail"]}
                       for k in knowledge if k["category"] == "non_negotiable"]
    learned_docs = db.list_learned_docs(partner_id)
    doc_sources = db.list_doc_sources(partner_id)

    out_dir = (output_dir or _DEFAULT_OUTPUT) / f"{slug}-rds-expert"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "reference").mkdir()

    env = Environment(loader=FileSystemLoader(str(_SKILL_BASE)), keep_trailing_newline=True)

    ctx = {
        "slug": slug,
        "name": name,
        "description": "",
        "partner_id": partner_id,
        "port": int(os.environ.get("TPS_PORT", "8771")),
        "ticket_count": len(tickets),
        "release_count": len(releases),
        "domain_count": len(domains),
        "releases": releases,
        "domains": domains,
        "non_negotiables": non_negotiables,
        "operators": operators,
        "release_operators": release_operators,
        "jira_config": jira_config,
        "knowledge_count": len(knowledge),
        "learned_docs_count": len(learned_docs),
        "doc_sources": doc_sources,
    }

    skill_md = env.get_template("SKILL.md.j2").render(ctx)
    (out_dir / "SKILL.md").write_text(skill_md)

    readme = env.get_template("README.md.j2").render(ctx)
    (out_dir / "README.md").write_text(readme)

    resp_template = (_SKILL_BASE / "response-template.md").read_text()
    (out_dir / "reference" / "response-template.md").write_text(resp_template)

    rel_md = _render_releases_md(name, slug, releases, release_operators)
    (out_dir / "reference" / f"{slug}-releases.md").write_text(rel_md)

    exc_md = _render_support_exceptions_md(name, tickets, domains, releases)
    (out_dir / "reference" / "support-exceptions.md").write_text(exc_md)

    if knowledge:
        know_md = _render_knowledge_md(name, knowledge)
        (out_dir / "reference" / "knowledge.md").write_text(know_md)

    if learned_docs:
        docs_md = _render_learned_docs_md(name, learned_docs)
        (out_dir / "reference" / "partner-documents.md").write_text(docs_md)

    # OPENAI.md is the portable context manifest consumed by the OpenAI
    # Architect adapter. It also remains useful reference material for the
    # Claude backend.
    openai_md = skill_md
    if openai_md.startswith("---"):
        _, _, openai_md = openai_md.split("---", 2)
        openai_md = openai_md.lstrip("\n")
    openai_md = openai_md.replace(f"~/.claude/skills/{slug}-rds-expert/", "./")
    (out_dir / "OPENAI.md").write_text(openai_md)

    # Claude Code emits structured lifecycle events. These hooks are generated
    # only as a Claude adapter artifact; OpenAI uses the Architect service
    # callback path instead. Both write through the same topic/audit API.
    hook_base = f"http://localhost:{ctx['port']}/hooks"
    hook_cfg = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "http", "url": f"{hook_base}/session-start"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "http", "url": f"{hook_base}/prompt-submit"}]}],
            "Stop": [{"hooks": [{"type": "http", "url": f"{hook_base}/stop"}]}],
            "SessionEnd": [{"hooks": [{"type": "http", "url": f"{hook_base}/session-end"}]}],
        }
    }
    claude_dir = out_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "settings.json").write_text(json.dumps(hook_cfg, indent=2) + "\n")

    version = db.bump_skill_version(partner_id)
    db.log(partner_id, "skill_generated", f"Skill v{version} generated at {out_dir}")
    return out_dir


def _render_releases_md(name: str, slug: str,
                        releases: list[dict], release_operators: list[dict] | None = None) -> str:
    lines = [f"# {name} — Release Quick Reference", ""]

    if releases:
        lines.append("## Release-to-OCP mapping")
        lines.append("")
        lines.append("| Release | OCP Version | Status | GA Date | EOL | Partner Build | Docs |")
        lines.append("|---------|-------------|--------|---------|-----|---------------|------|")
        for r in releases:
            status = (r.get("release_status") or "ga").upper()
            ga = r.get("ga_date") or "—"
            eol = r.get("eol_date") or "—"
            doc = f"[docs]({r['doc_url']})" if r.get("doc_url") else "—"
            lines.append(f"| {r['release_name']} | {r['ocp_version']} | {status} | {ga} | {eol} | {r['partner_build']} | {doc} |")
        lines.append("")

    if release_operators:
        lines.append("## Per-release operator versions")
        lines.append("")
        lines.append("| Release | Operator | Pinned Version |")
        lines.append("|---------|----------|----------------|")
        for ro in release_operators:
            lines.append(f"| {ro['release_name']} | {ro['operator_name']} | {ro.get('pinned_version') or '—'} |")
        lines.append("")

    return "\n".join(lines)


def _render_support_exceptions_md(name: str, tickets: list[dict],
                                  domains: list[dict], releases: list[dict]) -> str:
    lines = [f"# {name} — Support Exceptions (ECOPS Knowledge Base)", ""]

    by_domain: dict[str, list[dict]] = {}
    uncategorised = []
    for t in tickets:
        dname = t.get("domain_name")
        if dname:
            by_domain.setdefault(dname, []).append(t)
        else:
            uncategorised.append(t)

    for dname in sorted(by_domain):
        lines.append(f"## {dname}")
        lines.append("")
        lines.append("| ECOPS Key | Release | Summary | Resolution |")
        lines.append("|-----------|---------|---------|------------|")
        for t in sorted(by_domain[dname], key=lambda x: x["ecops_key"]):
            rel = t.get("release_name", "—") or "—"
            lines.append(f"| {t['ecops_key']} | {rel} | {t['summary']} | {t['resolution']} |")
        lines.append("")

    if uncategorised:
        lines.append("## Uncategorised")
        lines.append("")
        lines.append("| ECOPS Key | Release | Summary | Resolution |")
        lines.append("|-----------|---------|---------|------------|")
        for t in sorted(uncategorised, key=lambda x: x["ecops_key"]):
            rel = t.get("release_name", "—") or "—"
            lines.append(f"| {t['ecops_key']} | {rel} | {t['summary']} | {t['resolution']} |")
        lines.append("")

    lines.append("## Full ECOPS Index")
    lines.append("")
    lines.append("| ECOPS Key | Domain | Release | Summary | Resolution |")
    lines.append("|-----------|--------|---------|---------|------------|")
    for t in sorted(tickets, key=lambda x: x["ecops_key"]):
        dom = t.get("domain_name", "—") or "—"
        rel = t.get("release_name", "—") or "—"
        lines.append(f"| {t['ecops_key']} | {dom} | {rel} | {t['summary']} | {t['resolution']} |")
    lines.append("")

    return "\n".join(lines)


def _render_knowledge_md(name: str, knowledge: list[dict]) -> str:
    lines = [f"# {name} — Partner Knowledge Base", ""]

    by_cat: dict[str, list[dict]] = {}
    for k in knowledge:
        by_cat.setdefault(k["category"], []).append(k)

    cat_titles = {
        "configuration": "Configuration",
        "architecture": "Architecture",
        "limitation": "Limitations",
        "validated_finding": "Validated Findings",
        "non_negotiable": "Non-Negotiables",
    }

    for cat in ["non_negotiable", "configuration", "architecture", "limitation", "validated_finding"]:
        entries = by_cat.get(cat, [])
        if not entries:
            continue
        lines.append(f"## {cat_titles.get(cat, cat)}")
        lines.append("")
        for e in entries:
            detail = f" — {e['detail']}" if e.get("detail") else ""
            lines.append(f"- {e['fact']}{detail}")
        lines.append("")

    return "\n".join(lines)


def _render_learned_docs_md(name: str, learned_docs: list[dict]) -> str:
    lines = [f"# {name} — Partner Document Library", ""]
    lines.append(f"{len(learned_docs)} documents indexed from partner document sources.")
    lines.append("")

    lines.append("## Document Index")
    lines.append("")
    lines.append("| Document | Folder | Size |")
    lines.append("|----------|--------|------|")
    for d in learned_docs:
        size_kb = int(d.get("file_size", 0)) // 1024
        size = f"{size_kb} KB" if size_kb else "—"
        lines.append(f"| {d['name']} | {d.get('folder_path', '')} | {size} |")
    lines.append("")

    for d in learned_docs:
        lines.append(f"## {d['name']}")
        lines.append("")
        if d.get("url"):
            lines.append(f"Source: {d['url']}")
            lines.append("")
        if d.get("content_extract"):
            lines.append(d["content_extract"])
            lines.append("")

    return "\n".join(lines)
