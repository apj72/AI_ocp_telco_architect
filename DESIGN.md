# OpenAI Telco Architect — migration design

## Review summary

The source application already has the right product shape: FastAPI routes, a
SQLite partner knowledge base, Jira/document import, deterministic topic
routing, generated reference files, backups, and a browser workspace. The
provider coupling was concentrated in the embedded PTY (`tps/terminal.py`),
Claude-specific generated files and hooks (`tps/skill_gen.py`), the startup
environment, and documentation/UI copy.

## OpenAI architecture

```text
Browser xterm.js
       │ WebSocket (line-oriented prompts)
FastAPI /ws/terminal/{partner}
       │
OpenAI Architect adapter
       ├── generated OPENAI.md + reference/*.md
       ├── Responses API
       │     └── previous_response_id (session continuity)
       └── optional future tools: Jira, document retrieval, topic mutations
```

The adapter deliberately does not launch a local shell or provider CLI. Each
browser connection is an isolated model session. Partner context is loaded
from the generated directory and passed as developer instructions; the API
response ID carries the conversation forward without writing model state into
the browser.

## Configuration

Required:

```bash
export OPENAI_API_KEY=...
```

Optional:

```bash
export OPENAI_MODEL=gpt-5.5
export OPENAI_MAX_OUTPUT_TOKENS=1800
```

The model is configurable so deployments can choose a different current model
without changing application code.

## Deliberate migration choices

- Existing database and REST API are retained to keep the migration low-risk.
- Generated `OPENAI.md` replaces `CLAUDE.md`; it is context, not a CLI plugin.
- Claude lifecycle hooks are no longer required for the embedded session.
- `previous_response_id` provides multi-turn continuity for one WebSocket.
- The existing xterm.js UI is retained as a compatibility layer. It now behaves
  as a keyboard-driven chat console rather than exposing a server shell.
- OpenAI SDK failures are surfaced in the console and do not crash FastAPI.

## Next implementation stage

The first production hardening step should add explicit OpenAI function tools
for topic selection, interaction logging, knowledge creation, and Jira access.
Those tools should call the existing database/service functions and enforce
partner ownership server-side. The current implementation keeps those actions
out of the model until their authorization and audit contracts are defined.

