# Development Roadmap

## Recently Completed (pre-OS update, 2026-07-13)

- **Operators tab** — full CRUD, optional bootstrap auto-seed, skill template integration
- **Knowledge pipeline UI** — Review Queue (folder-grouped, resizable columns, in-place approve/ignore with colour feedback), Processing Queue (separate view for approved docs)
- **Process with Architect button** — kicks the Architect terminal to extract knowledge from approved docs using skill template instructions
- **ECOPS resolution mapping** — Jira proxy statuses translated to actual meanings (Done-Errata → Support Exception, Not a Bug → Non-Impacting). Data migration, import-time translation, skill template documentation
- **`sendToArchitect()` helper** — reusable JS function to start terminal + inject prompt, useful for future automation

---

## Security Hardening

### Critical

1. **Add authentication layer**
   - No auth on any endpoint including the WebSocket terminal (full shell access)
   - Simplest: env var `TPS_SECRET` checked via cookie/header, FastAPI middleware
   - Files: `tps/app.py` (middleware), `templates/login.html` (new), `static/app.js` (token header)

2. **Encrypt credentials at rest**
   - Jira tokens and SharePoint auth cookies stored plaintext in SQLite (`partner_jira_config.jira_token`, `auth_sources.auth_value`)
   - Use `cryptography.fernet` with a master key from env var
   - Files: `tps/db.py` (encrypt on write, decrypt on read)

3. **Stop leaking credentials into HTML**
   - `partner.html:434,438` — Jira token echoed back in form `value` attribute
   - `index.html:70` — `jira_config|tojson` embeds full config (including token) in onclick handler
   - Fix: never render tokens back to browser; use placeholder "configured" text instead

4. **Bind to localhost by default**
   - `scripts/start.sh:8` binds to `::` (all interfaces) — exposes everything to the network
   - Change default to `127.0.0.1`; require explicit `TPS_HOST=::` to open up

### High

5. **XSS hardening** ✅
   - All `innerHTML` assignments audited — `esc()` applied to every user-content interpolation (`browseTo()` paths/names, error messages, active topic title, topic card status)
   - Content-Security-Policy header set via FastAPI middleware

6. **Path traversal fix**
   - `app.py:829-836` — workspace file serving uses string-based prefix check
   - Replace with `Path.is_relative_to()` (Python 3.9+)

### Medium

7. **Security headers** — add CORS middleware, CSP, X-Frame-Options, X-Content-Type-Options
8. **Database file permissions** ✅ — `os.chmod(path, 0o600)` in `db.py __init__`
9. **Rate limiting** — add `slowapi` or similar for API endpoints
10. **HTTPS enforcement** — add HSTS header, redirect HTTP to HTTPS when TLS configured
11. **Pin dependency versions** ✅ — `requirements.txt` pinned to `==` exact versions

---

## Feature Improvements

### UI/UX

12. **Search and filter on tables**
    - Tickets, knowledge, operators, releases all lack search/filter
    - Client-side `<input type="search">` with JS filtering per table
    - Priority: tickets table (can have hundreds of entries)

13. **Column sorting**
    - Click column header to sort ascending/descending
    - Reuse pattern across all data tables

14. **Keyboard shortcuts**
    - Ctrl+K for search, Escape to close modals, Tab navigation
    - Low effort, high value for power users

15. **Loading states**
    - Skill generation, Jira import, doc learning show no progress indicator
    - Add spinner/progress bar for long operations

16. **Pop-out Architect terminal**
    - Separate resizable window for the terminal
    - Deferred from earlier session — user said "hold that thought"

17. **Tab grouping**
    - Tabs are cluttered — consider grouping: Config (releases, operators), Data (tickets, domains), Research (topics, knowledge, doc sources)

### Data Model

18. **Release-to-operator version pinning**
    - New `release_operator_versions` junction table
    - Answer: "which operator versions are required for release 25R3?"
    - Currently operators are global to partner, not per-release

19. **Knowledge linking to releases/domains**
    - `knowledge_release` and `knowledge_domain` junction tables
    - Answer: "what knowledge applies to release 26R1?"

21. **ECOPS ticket relationships**
    - Track duplicates, blockers, related tickets between ECOPS entries

22. **Document change detection**
    - Compare `modified_at` on incremental sync to flag changed docs for re-review
    - Currently re-learning doesn't detect content changes

### Skill Quality

23. **Auto-generate OCP doc URLs**
    - When generating skill, compute `docs.openshift.com/container-platform/{version}/` from release data
    - Currently relies on manual `doc_url` entry per release

24. **Release comparison delta**
    - Compute what changed between releases: operator version changes, new tickets
    - Add to skill reference for cross-release analysis

25. **Document index in skill**
    - Structured YAML frontmatter index at top of `partner-documents.md`
    - Enables the Architect to search learned docs by topic

27. **ECOPS cross-indexed by release**
    - Skill currently groups by domain only — add per-release grouping
    - "All ECOPS affecting OCP 4.18" as a quick lookup

### Workflow Automation

28. **Auto-regen skill on data change**
    - When tickets/operators/knowledge/releases change, regenerate skill automatically
    - Or at minimum, show "skill outdated" badge

29. **Incremental Jira sync**
    - Currently one-shot import only — if ticket status changes in Jira, app doesn't know
    - Add scheduled sync: poll Jira for new/updated tickets

30. **Background task queue for doc learning**
    - Document learning blocks the browser during extraction
    - Move to background with progress polling (or use streaming better)

31. **OCP lifecycle auto-lookup**
    - When user enters OCP version, auto-fill GA/EOL dates from `api.openshift.com`
    - Pre-fill form fields to reduce manual data entry

32. **Bulk approval in Review Queue**
    - "Select all in folder, mark approved" for batch operations
    - Currently one doc at a time

### Integrations

33. **Confluence as doc source**
    - Some partners document architecture in Confluence, not SharePoint
    - Already have httpx + auth_sources pattern, mostly plug-and-play

34. **GitHub/GitLab repo browsing**
    - Browse partner blueprint repos; learn architecture docs, CRDs, release notes
    - New source type `github_repo` with PAT auth

35. **Slack/Teams notifications**
    - Webhook on skill regen, new ticket import, topic resolution
    - Add webhook URL to partner config

### Testing & Deployment

36. **Test coverage**
    - Zero tests currently — fragile codebase
    - Priority: `tps/db.py` (data integrity), `tps/skill_gen.py` (Jinja2 rendering), API routes
    - Add pytest + conftest with in-memory SQLite fixture

37. **Docker deployment**
    - Currently `scripts/start.sh` with manual venv setup
    - Add Dockerfile + docker-compose.yml for easy deployment

38. **Database backup strategy**
    - SQLite in `data/partners.db` with no backup
    - Add daily backup script or S3 sync

39. **Systemd service unit**
    - Running as `nohup` is fragile — doesn't auto-start on reboot
    - Create `/etc/systemd/system/tps.service`

---

## Priority Matrix

| Priority | Items | Rationale |
|----------|-------|-----------|
| **P0 — Before sharing** | 1-4 (auth, encryption, credential leak, localhost binding) | Security fundamentals |
| **P1 — Next sprint** | 12-13 (search/sort), 28 (auto-regen skill), 5-6 (XSS/path traversal) | Usability + security |
| **P2 — Near term** | 18 (release-operator mapping), 29 (Jira sync), 15 (loading states), 16 (pop-out terminal) | Feature gaps |
| **P3 — Future** | 33-35 (integrations), 36-39 (testing/deployment), 19-22 (data model) | Scale & robustness |
