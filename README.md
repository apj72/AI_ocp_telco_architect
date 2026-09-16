# Telco Partner Skills (TPS) Framework

A web application for building and managing partner-specific OpenShift Telco RDS knowledge bases. TPS aggregates partner data from Jira, SharePoint, and direct entry into structured knowledge bases, then loads that context into an OpenAI Responses API Architect session.

The problem: partner-specific RDS knowledge — support exceptions, operator version pins, architecture decisions, configuration constraints — is scattered across Jira tickets, SharePoint documents, and tribal knowledge. There's no structured way to give an AI assistant the full picture when reviewing partner manifests or assessing deviations.

TPS solves this by providing a per-partner knowledge base with an embedded OpenAI Architect console. Each partner gets isolated data (tickets, domains, releases, operators, knowledge entries, learned documents, research topics), and the framework generates a portable context directory that loads all of it into the model session.

> **[Read the User Guide](docs/user-guide.html)** — step-by-step walkthrough with architecture diagrams covering setup, features, security, and deployment.

## Key Features

- **Partner Management** — create and manage multiple partners, each with isolated data
- **ECOPS Ticket Import** — pull support exception tickets from Jira, categorise by domain, map to releases
- **Knowledge Base** — curated facts (architecture, configuration, limitations, validated findings, non-negotiables) from documents, research, or direct entry
- **Document Learning** — connect SharePoint sites or web pages, browse folder structures, extract content into the knowledge base
- **Research Topics** — track ongoing research with notes, linked sources, and conversation logs that persist across sessions
- **Context Generation** — produce a complete OpenAI Architect context directory with all partner knowledge embedded
- **Architect Console** — embedded OpenAI Responses API session on each partner page, running with full partner context
- **Release & Operator Tracking** — map partner releases to OCP versions with GA/EOL dates; pin operator versions per release

## Quick Start

**Prerequisites:** Python 3.10+ and an OpenAI API key in `OPENAI_API_KEY`.

```bash
git clone <repo-url>
cd tps_framework
pip install -r requirements.txt
./scripts/start.sh
# Open http://localhost:8771
```

```bash
# Custom port
TPS_PORT=9000 ./scripts/start.sh

# Stop
./scripts/stop.sh
```

## Setup Guide

1. **Start the app** — run `./scripts/start.sh` and open `http://localhost:8771`
2. **Create a partner** — click the gear icon, enter the partner name
3. **Configure Jira** — on the partner page, open Jira Settings. Choose MCP mode (uses atlassian-rovo MCP server, no token needed) or API Key mode (Jira URL + email + API token). Set the ECOPS project key and version prefix
4. **Import tickets** — click "Import from Jira" to pull support exception tickets. Assign domains and releases as they come in
5. **Add knowledge** — enter facts directly, or connect document sources (SharePoint/web) and use the Review Queue to learn documents
6. **Generate context** — click "Generate Skill" to produce an OpenAI Architect context directory under `output/`
7. **Configure context** — the embedded Architect loads the generated directory automatically:
   ```bash
   export OPENAI_TPS_CONTEXT=/path/to/output/<partner>-rds-expert
   ```
8. **Use the Architect terminal** — the embedded terminal on each partner page loads the generated skill automatically. The Architect can create research topics, log conversations, and update the knowledge base as it works

## Backup & Restore

TPS automatically backs up the SQLite database and workspace on startup, following a weekday schedule:

| Day | File | Retention |
|-----|------|-----------|
| Monday | `weekly_YYYY-MM-DD.zip` | Last 4 weeks |
| Tue–Fri | `daily.zip` | Overwritten each day |

Backups are stored in `data/backups/` and validated with SQLite `PRAGMA integrity_check` before being accepted.

**Manual backup/restore** is available from Settings in the web UI. Manual backups are timestamped and never auto-deleted. Restoring creates a safety backup of the current state first.

**CLI backup** for cron jobs:

```bash
./scripts/backup.sh                  # Default destination: data/backups/
./scripts/backup.sh /mnt/nas/tps     # Custom destination
```

Both methods bundle the database and full workspace (`~/tps-workspace`) into a single zip, using SQLite's online backup API for a consistent copy without stopping the server.

> **Note:** If restoring on a different machine, the same `TPS_MASTER_KEY` is required to decrypt stored Jira tokens and auth credentials.

## Security

### Default Posture

TPS binds to `127.0.0.1` (localhost only) by default. No authentication is required for local development. Before exposing on a network, configure password protection and encryption.

### Password Protection

```bash
export TPS_SECRET=your-password-here
./scripts/start.sh
```

All routes redirect to `/login` until authenticated. The WebSocket terminal returns 403 for unauthenticated requests. Unset means no auth (local dev only).

### Encryption at Rest

```bash
# Generate a Fernet key (one-time, save it somewhere safe)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

export TPS_MASTER_KEY=<key from above>
```

Jira API tokens and auth source credentials are encrypted with the Fernet key before being stored in SQLite. Existing plaintext rows are encrypted on next save. Without the key, credentials are stored in plaintext.

### Credential Handling

- Jira API tokens are **never sent back to the browser** — the token form shows a placeholder when a token is already configured
- Leave the token field blank when editing to preserve the existing token
- Auth source credentials (SharePoint cookies, bearer tokens) follow the same encrypt-at-rest pattern

### Security Headers

TPS sets the following headers on all responses:
- `Content-Security-Policy` — restricts script/style sources to self, blocks object embeds and framing
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: same-origin`

### XSS Prevention

All user-supplied content rendered via JavaScript is escaped through a dedicated `esc()` function before innerHTML insertion, covering topic titles, directory names, breadcrumbs, and error messages.

### Database File Permissions

The SQLite database is created with mode `0600` (owner read/write only), preventing other users on a shared system from reading partner data or credentials.

### Dependency Pinning

All Python dependencies in `requirements.txt` are pinned to exact versions to prevent supply-chain attacks via malicious package updates.

### Data Isolation

Each deployment is single-user. No data sharing between partners or users. The SQLite database and generated skill outputs are gitignored — credentials and commercially sensitive information stay local to the machine.

## Deployment

### Local Development

```bash
./scripts/start.sh
```

### Docker / Podman

```bash
docker-compose up -d
```

The container runs as a non-root user (`tps`), exposes port 8000, and persists data to a `/data` volume. Set `TPS_SECRET` and `TPS_MASTER_KEY` via environment variables.

### Systemd

A service unit is provided at `scripts/tps.service`. Copy to `/etc/systemd/system/`, adjust paths, and enable:

```bash
sudo systemctl enable --now tps
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `TPS_SECRET` | Password for web UI access | _(none — no auth)_ |
| `TPS_MASTER_KEY` | Fernet key for encrypting credentials at rest | _(none — plaintext)_ |
| `TPS_HOST` | Bind address | `127.0.0.1` |
| `TPS_PORT` | Listen port | `8771` |
| `TPS_WORKSPACE` | Working directory for topics and research | `~/tps-workspace` |

## Project Structure

```
├── tps/                     # Python package
│   ├── app.py               # FastAPI routes + WebSocket terminal
│   ├── backup.py            # Backup/restore with validation
│   ├── db.py                # SQLite schema + queries
│   ├── skill_gen.py         # Generates OpenAI Architect context directories
│   ├── terminal.py          # WebSocket bridge for the OpenAI Responses API
│   ├── doc_browse.py        # SharePoint/web document browsing
│   ├── auth_capture.py      # Browser-based auth capture
│   ├── research.py          # Source fetching + content extraction
│   ├── ocp_versions.py      # OpenShift version API client
│   ├── jira_import.py       # Jira REST client
│   └── topic_router.py      # Research topic routing
├── templates/               # Jinja2 HTML templates
├── static/                  # CSS + JS
├── skill-base/              # Skill templates (Jinja2)
├── tests/                   # pytest test suite
├── scripts/                 # start.sh, stop.sh, tps.service
├── data/                    # SQLite database (gitignored)
├── output/                  # Generated skills (gitignored)
├── Dockerfile               # Container image
└── docker-compose.yml       # Container orchestration
```

## Generated Skill Structure

```
output/<partner>-rds-expert/
├── SKILL.md                         # Skill manifest (installable)
├── OPENAI.md                        # Project context
├── README.md                        # Installation instructions
└── reference/
    ├── <partner>-releases.md        # Release mapping & operator pins
    ├── support-exceptions.md        # ECOPS knowledge base by domain
    ├── knowledge.md                 # Curated knowledge entries
    ├── partner-documents.md         # Learned document extracts
    └── response-template.md         # Response structure template
```

## Jira Integration

Each partner stores its own Jira configuration. Two modes:

- **MCP mode** — uses the Atlassian Rovo MCP server (no API token needed, requires MCP setup)
- **API Key mode** — direct Jira REST API with email + API token

Configure per partner via "Jira Settings" on the partner page.

## Dependencies

- **fastapi** + **uvicorn** — web framework and ASGI server
- **jinja2** — HTML and skill template rendering
- **httpx** — HTTP client for Jira API and document fetching
- **cryptography** — Fernet encryption for credentials at rest
- **python-multipart** — form data parsing
- **playwright** — browser-based auth capture for SharePoint
- **docling**, **pypdf**, **python-docx**, **python-pptx** — document content extraction
- **pytest** — test suite

No database server required. SQLite is used for all persistent storage.

## Concurrent Sessions

You can safely open multiple browser tabs or sessions against the same running TPS server — for example, working on two different partner topics side by side. SQLite is configured with WAL mode and a 5-second busy timeout, so concurrent reads and writes are handled transparently. There is no need to run multiple server instances.
