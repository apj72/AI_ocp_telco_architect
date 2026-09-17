from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ArchitectEvent:
    """Normalized event shape reserved for the streaming backend contract."""

    type: str
    text: str = ""
    provider: str = ""
    model: str = ""


class ArchitectBackend(Protocol):
    provider: str

    async def serve(self, websocket, cwd: str, model: str) -> None:
        """Serve one browser session until disconnect."""
