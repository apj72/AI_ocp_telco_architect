from __future__ import annotations

from pathlib import Path


def load_context(cwd: str) -> str:
    root = Path(cwd)
    parts = []
    for name in ("OPENAI.md", "AI.md", "SKILL.md", "README.md"):
        path = root / name
        if path.is_file():
            parts.append(f"\n--- {name} ---\n{path.read_text(errors='replace')[:24000]}")
    reference = root / "reference"
    if reference.is_dir():
        for path in sorted(reference.glob("*.md")):
            parts.append(f"\n--- reference/{path.name} ---\n{path.read_text(errors='replace')[:24000]}")
    return "".join(parts)[:100000]


def instructions(cwd: str, provider: str) -> str:
    return f"""You are the {provider.title()} Telco Architect for the partner knowledge base below.
Use the supplied partner facts as authoritative context. Be precise about release
versions and support exceptions. If the context does not contain an answer, say
what is missing and suggest a verifiable next step. Do not invent Jira tickets,
operator versions, or support policy. Keep answers practical and structured.

Topic policy: the application routes each session to a user-selected research
topic. Continue the current topic unless the user explicitly asks to switch.

Working directory: {cwd}
Partner context:
{load_context(cwd)}
"""
