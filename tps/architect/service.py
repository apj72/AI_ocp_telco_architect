from __future__ import annotations

from tps.architect.claude_backend import ClaudeBackend
from tps.architect.config import ArchitectConfig
from tps.architect.openai_backend import OpenAIBackend
from tps.architect.base import PromptHook, ResponseHook


def backend_for(config: ArchitectConfig):
    return OpenAIBackend() if config.provider == "openai" else ClaudeBackend()


async def architect_handler(websocket, cwd: str, provider: str | None = None,
                            model: str | None = None,
                            on_prompt: PromptHook | None = None,
                            on_response: ResponseHook | None = None) -> None:
    try:
        config = ArchitectConfig.from_env(provider=provider, model=model)
    except ValueError as exc:
        await websocket.send_text(f"Architect configuration error: {exc}\r\n")
        await websocket.close(code=1008)
        return
    available, reason = config.availability()
    if not available:
        await websocket.send_text(
            f"{config.provider.title()} backend unavailable: {reason}.\r\n"
        )
        await websocket.close(code=1011)
        return
    await backend_for(config).serve(
        websocket, cwd, config.model,
        on_prompt=on_prompt,
        on_response=on_response,
    )
