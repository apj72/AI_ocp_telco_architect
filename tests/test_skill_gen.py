import json

import pytest
from tps.skill_gen import generate_skill, _render_releases_md, _render_support_exceptions_md


RELEASES = [
    {"release_name": "25R3", "ocp_version": "4.17", "release_status": "ga",
     "ga_date": "2025-01-01", "eol_date": "2026-01-01", "partner_build": "25.3.0",
     "doc_url": "https://docs.example.com"},
]

DOMAINS = [{"id": "d1", "name": "networking"}]

TICKETS = [
    {"ecops_key": "ECOPS-100", "summary": "SRIOV deviation", "resolution": "Support Exception",
     "release_name": "25R3", "domain_name": "networking", "labels": ""},
    {"ecops_key": "ECOPS-101", "summary": "Another issue", "resolution": "",
     "release_name": None, "domain_name": "networking", "labels": ""},
]


def test_render_releases_has_header():
    md = _render_releases_md("TestCo", "testco", RELEASES)
    assert "# TestCo — Release Quick Reference" in md


def test_render_releases_release_mapping():
    md = _render_releases_md("TestCo", "testco", RELEASES)
    assert "Release-to-OCP mapping" in md
    assert "25R3" in md
    assert "4.17" in md


def test_render_releases_empty():
    md = _render_releases_md("TestCo", "testco", [])
    assert "# TestCo" in md


def test_render_releases_per_release_operators():
    release_operators = [
        {"release_name": "25R3", "operator_name": "sriov-network-operator",
         "pinned_version": "4.17.0-202501"},
    ]
    md = _render_releases_md("TestCo", "testco", RELEASES,
                             release_operators=release_operators)
    assert "Per-release operator versions" in md
    assert "sriov-network-operator" in md
    assert "4.17.0-202501" in md


def test_render_support_exceptions_has_header():
    md = _render_support_exceptions_md("TestCo", TICKETS, DOMAINS, RELEASES)
    assert "# TestCo — Support Exceptions" in md


def test_render_support_exceptions_resolved_section():
    md = _render_support_exceptions_md("TestCo", TICKETS, DOMAINS, RELEASES)
    assert "Support Exception" in md
    assert "ECOPS-100" in md


def test_render_support_exceptions_open_section():
    md = _render_support_exceptions_md("TestCo", TICKETS, DOMAINS, RELEASES)
    assert "ECOPS-101" in md


def test_render_support_exceptions_no_tickets():
    md = _render_support_exceptions_md("TestCo", [], DOMAINS, RELEASES)
    assert "# TestCo" in md


def test_generate_skill_includes_claude_lifecycle_hooks(db, partner, tmp_path, monkeypatch):
    monkeypatch.setenv("TPS_PORT", "9123")
    out_dir = generate_skill(db, partner["id"], output_dir=tmp_path)
    settings = json.loads((out_dir / ".claude" / "settings.json").read_text())
    hooks = settings["hooks"]
    assert set(hooks) == {"SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"}
    assert "localhost:9123/hooks/session-start" in str(hooks["SessionStart"])
