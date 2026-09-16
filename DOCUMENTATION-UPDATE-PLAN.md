# Documentation update plan for selectable AI backends

## Purpose

The current documentation describes the OpenAI migration, but it does not yet
describe the intended provider-neutral product. It also contains contradictory
legacy instructions: the README is OpenAI-focused, while parts of the HTML
guide still refer to Claude, a provider CLI, `/mcp`, lifecycle hooks, and
symlinking into `~/.claude/skills`.

Documentation should be updated after Claude/OpenAI switching works end to end,
so that examples, screenshots, configuration names, and troubleshooting steps
describe tested behavior rather than the planned architecture.

## Documentation inventory and required treatment

| Document | Current role | Required update |
|---|---|---|
| `README.md` | Landing page, quick start, deployment reference | Make provider-neutral; document `AI_PROVIDER`, provider credentials, model settings, capability differences, and the supported default. |
| `docs/user-guide.html` | Full user-facing guide | Rewrite installation, provider selection, Architect sessions, Jira/MCP behavior, generated context, security, deployment, and troubleshooting. Remove invented CLI instructions. |
| `DESIGN.md` | OpenAI migration design | Rename/reframe as provider-neutral architecture; retain OpenAI details in a backend subsection and add Claude transport behavior. |
| `IMPLEMENTATION-PLAN.md` | Engineering plan | Mark completed phases and link to the final provider contract and documentation requirements. |
| `ROADMAP.md` | Product backlog | Add provider selection, backend parity, capability discovery, and provider-specific tool support. |
| `OPENAI.md` | Project context | Replace with provider-neutral project context, or rename to `AI.md` once the selectable architecture is canonical. |
| `skill-base/SKILL.md.j2` | Generated partner context | Remove provider-specific assumptions; describe available tools/capabilities dynamically. |
| `skill-base/README.md.j2` | Generated context instructions | Explain that context is loaded by the selected backend and is not installed into a provider-specific directory. |
| `docs/screenshots/*` | User-guide visuals | Recapture provider selector, active provider/model, Claude session, OpenAI session, errors, and generated context. |
| Inline UI copy/templates | Product labels and help text | Replace “terminal” where it means chat session; show provider/model and capability status consistently. |

## Content changes by topic

### 1. Product overview

- Use “AI Architect” or “Architect session” as the provider-neutral term.
- Explain that Claude and OpenAI are selectable backends.
- Clarify which behavior is common to both providers: partner context,
  topics, audit logging, knowledge base, and Jira/document workflows.
- Explain that provider/model availability depends on local credentials and
  configured backend capabilities.

### 2. Installation and configuration

Document the common configuration first:

```bash
AI_PROVIDER=openai          # or claude
OPENAI_MODEL=gpt-5.5        # when AI_PROVIDER=openai
CLAUDE_MODEL=...            # when AI_PROVIDER=claude
OPENAI_API_KEY=...
CLAUDE_COMMAND=claude
```

The final names must match the implemented configuration module. Explain that
credentials are environment/secret-manager configuration, never SQLite data or
generated partner context. Include a provider readiness check and the expected
failure messages for missing credentials.

### 3. Selecting a provider and model

Add a dedicated user-guide section covering:

1. Application default provider.
2. Partner default provider.
3. Per-session override.
4. Model selection and provider capability display.
5. What happens when a selected provider is unavailable.
6. Whether switching creates a new conversation or continues an existing one.

The documentation must state the actual session rule. The recommended rule is
to start a new backend session when the provider changes and preserve the prior
conversation as read-only history.

### 4. Architect sessions

Replace “embedded terminal” language with “Architect console/session” where no
shell is exposed. Document the normalized experience and the provider-specific
differences:

- Claude: local CLI/PTY transport, if retained.
- OpenAI: Responses API transport and response state.
- Both: partner context loading, topic routing, errors, cancellation, and
  session end behavior.

Document that a provider session must not be assumed to have shell access or
the same tools as another provider.

### 5. Generated context and skills

- Describe generated context as portable partner reference material.
- Remove `~/.claude/skills` installation instructions.
- Explain `OPENAI.md`/`AI.md` naming after the final implementation decision.
- Document which files are generated and which are safe to share.
- State that credentials, live session IDs, and conversation history are not
  embedded in generated context.

### 6. Jira, MCP, and tools

The current guide incorrectly treats an OpenAI Architect CLI and `/mcp` as
available behavior. Replace this with an explicit capability matrix:

| Capability | Claude backend | OpenAI backend | Common UI/API path |
|---|---|---|---|
| Partner context | yes | yes | generated context loader |
| Topic routing | yes | yes | ArchitectService |
| Jira read | verify | verify | explicit backend tool |
| Jira mutation | verify/confirm | verify/confirm | confirmation-required tool |
| Web search | provider-dependent | provider-dependent | capability discovery |
| Local shell | explicitly state | explicitly state | disabled unless designed |

Only document capabilities that are implemented and tested. Provider-specific
setup instructions should be linked from the matrix rather than mixed into the
common workflow.

### 7. Security and operations

Update security documentation to cover:

- API keys and CLI credentials by provider.
- Prompt/context transmission to external model providers.
- Conversation state retention and provider-side storage behavior.
- Redaction of provider errors and sensitive partner content.
- Per-provider timeout, retry, cancellation, and rate-limit behavior.
- Audit logging of provider, model, session, and tool activity without storing
  secrets.

Update Docker, systemd, backup, and troubleshooting examples for all required
provider environment variables.

## Documentation sequence

### Before implementation is complete

- Keep this plan and the architecture/engineering plans current.
- Do not publish provider-specific UI screenshots as final documentation.
- Track terminology and configuration decisions in one place.

### After backend switching works

1. Verify the actual configuration names and precedence rules.
2. Verify both backends through the same user journeys.
3. Update generated templates and README first.
4. Rewrite the HTML user guide from the tested workflows.
5. Update design/roadmap status and troubleshooting.
6. Recapture screenshots from a clean installation.
7. Run link checks, HTML checks, and documentation smoke tests.
8. Commit documentation separately from backend implementation where possible.

## Acceptance criteria

- No user-facing document claims that only Claude or only OpenAI is supported.
- No guide instructs users to install a nonexistent provider CLI or use an
  unsupported `/mcp` command.
- Provider selection, model selection, credential setup, and fallback behavior
  are documented using tested commands and screenshots.
- Common features and provider-specific differences are clearly separated.
- Generated context documentation matches the files produced by
  `skill_gen.py`.
- README and HTML guide agree on defaults, ports, environment variables, and
  session behavior.
- A new user can configure either provider and start a session without reading
  source code.

