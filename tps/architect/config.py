from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


SUPPORTED_PROVIDERS = ("openai", "claude")


@dataclass(frozen=True)
class ArchitectConfig:
    provider: str
    model: str
    openai_model: str
    claude_model: str
    claude_command: str
    max_output_tokens: int

    @classmethod
    def from_env(cls, provider: str | None = None,
                 model: str | None = None) -> "ArchitectConfig":
        selected = (provider or os.environ.get("AI_PROVIDER", "openai")).strip().lower()
        if selected not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported AI provider '{selected}'. Choose: {', '.join(SUPPORTED_PROVIDERS)}"
            )
        openai_model = os.environ.get("OPENAI_MODEL", "gpt-5.5")
        claude_model = os.environ.get("CLAUDE_MODEL", "")
        selected_model = model or (openai_model if selected == "openai" else claude_model)
        return cls(
            provider=selected,
            model=selected_model,
            openai_model=openai_model,
            claude_model=claude_model,
            claude_command=os.environ.get("CLAUDE_COMMAND", "claude"),
            max_output_tokens=int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "1800")),
        )

    def availability(self) -> tuple[bool, str]:
        if self.provider == "openai":
            if os.environ.get("OPENAI_API_KEY"):
                return True, "OPENAI_API_KEY configured"
            return False, "OPENAI_API_KEY is not configured"
        if shutil.which(self.claude_command):
            return True, f"{self.claude_command} found in PATH"
        return False, f"{self.claude_command} not found in PATH"


def provider_catalog() -> list[dict]:
    """Return safe provider capabilities; never expose credentials."""
    rows = []
    for provider in SUPPORTED_PROVIDERS:
        config = ArchitectConfig.from_env(provider=provider)
        available, reason = config.availability()
        rows.append({
            "id": provider,
            "label": "OpenAI" if provider == "openai" else "Claude",
            "available": available,
            "reason": reason,
            "default_model": config.model,
            "configured_model": config.model,
        })
    return rows
