from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol


PromptHook = Callable[[str], Awaitable[str]]
ResponseHook = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ArchitectEvent:
    """Normalized event shape reserved for the streaming backend contract."""

    type: str
    text: str = ""
    provider: str = ""
    model: str = ""


class ArchitectBackend(Protocol):
    provider: str

    async def serve(self, websocket, cwd: str, model: str,
                   on_prompt: PromptHook | None = None,
                   on_response: ResponseHook | None = None) -> None:
        """Serve one browser session until disconnect."""
