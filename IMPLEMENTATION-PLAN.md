# Selectable AI implementation plan

## Objective

Make the Telco Architect provider-neutral so a user can select Claude or
OpenAI without changing the partner knowledge base, browser workflow, topic
routing, Jira/document features, or generated context.

## Target architecture

```text
Browser / partner session
          │
     ArchitectService
          │
   ┌──────┴────────┐
ClaudeBackend   OpenAIBackend
   │                 │
Claude CLI/PTY   Responses API
```

`ArchitectService` owns session lifecycle, prompt submission, topic routing,
interaction logging, and normalized events. Backends only translate those
operations into provider-specific transport and response handling.

## Provider contract

Create `tps/architect/` with:

- `base.py` — `ArchitectBackend` protocol and normalized events.
- `claude.py` — current PTY implementation moved behind the protocol.
- `openai.py` — current Responses API implementation moved behind the protocol.
- `service.py` — provider selection, session lifecycle, and error handling.
- `config.py` — validated provider/model configuration.

Normalized events should include `session_started`, `text_delta`,
`tool_activity`, `error`, and `session_ended`. This lets the frontend remain
provider-neutral and makes streaming possible for both backends.

## Selection model

Support three levels, in precedence order:

1. Explicit session selection from the partner page.
2. Partner default stored in the database.
3. Application default from `AI_PROVIDER`.

Suggested settings:

```bash
AI_PROVIDER=openai
OPENAI_MODEL=gpt-5.5
CLAUDE_COMMAND=claude
CLAUDE_MODEL=...
```

The UI should show provider and model before starting a session and display the
active selection in the Architect header. Do not store API keys in the database.

## Implementation phases

Current status: Phases 1–2 are implemented, and the session/audit portion of
Phase 3 is in progress. Provider-specific tools remain deliberately deferred.

### Phase 1 — Boundary and configuration

- Add provider configuration and validation.
- Define the backend protocol and normalized event types.
- Add unit tests for provider selection and invalid configuration.

### Phase 2 — Extract existing implementations

- Move the current OpenAI WebSocket logic into `OpenAIBackend`.
- Move the original Claude PTY logic into `ClaudeBackend`.
- Keep `/ws/terminal/{pid}` temporarily as a compatibility route.
- Add backend-independent WebSocket tests with mocked providers.

### Phase 3 — Topic and audit integration

- Create a provider-neutral session ID.
- Route every submitted prompt through `topic_router.py`.
- Log normalized prompts/responses using the existing interaction tables.
- Preserve the hard gate requiring user topic selection.
- Ensure all tool/database operations enforce partner ownership.

Implemented in the current slice: provider-neutral session creation, prompt
routing through `topic_router.py`, interaction creation/completion, active-topic
polling, and provider/model selection passed through the Architect WebSocket.

### Phase 4 — UI selection

- Add provider/model controls to the partner page.
- Add an `/api/providers` capability endpoint.
- Include active provider/model and session status in the UI.
- Make `sendToArchitect()` provider-neutral.
- Keep the xterm console initially; later consider a richer chat transcript.

### Phase 5 — Tools and production hardening

- Add explicit tools for topic mutation, knowledge creation, Jira access, and
  document processing.
- Add confirmation requirements for mutating actions.
- Add timeouts, cancellation, retry policy, and usage telemetry.
- Add redaction and security tests for provider errors and prompt content.
- Update user guide and deployment documentation.

## Acceptance criteria

- A user can select Claude or OpenAI before starting a partner session.
- The same generated partner context works with both providers.
- Topic routing and audit logging behave identically for both providers.
- A provider outage produces an in-app error without crashing FastAPI.
- No API key or provider credential is stored in SQLite or generated context.
- Existing non-AI tests remain green and both backends have mocked integration
  coverage.

## Initial delivery boundary

The first implementation should complete Phases 1–2 and expose selection via
environment configuration. UI selection and provider-specific tools should
follow after the backend contract is stable.
