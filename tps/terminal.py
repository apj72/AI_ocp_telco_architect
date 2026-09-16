"""WebSocket adapter for the OpenAI Architect session."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path


def _load_context(cwd: str) -> str:
    root = Path(cwd)
    parts = []
    for name in ("OPENAI.md", "SKILL.md", "README.md"):
        path = root / name
        if path.is_file():
            parts.append(f"\n--- {name} ---\n{path.read_text(errors='replace')[:24000]}")
    reference = root / "reference"
    if reference.is_dir():
        for path in sorted(reference.glob("*.md")):
            parts.append(f"\n--- reference/{path.name} ---\n{path.read_text(errors='replace')[:24000]}")
    return "".join(parts)[:100000]


def _instructions(cwd: str) -> str:
    return f"""You are the OpenAI Telco Architect for the partner knowledge base below.
Use the supplied partner facts as authoritative context. Be precise about release
versions and support exceptions. If the context does not contain an answer, say
what is missing and suggest a verifiable next step. Do not invent Jira tickets,
operator versions, or support policy. Keep answers practical and structured.

Topic policy: the application routes each session to a user-selected research
topic. Continue the current topic unless the user explicitly asks to switch.

Working directory: {cwd}
Partner context:
{_load_context(cwd)}
"""


def _response_text(response) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    return "\n".join(chunks) or "(The model returned no text.)"


async def terminal_handler(websocket, cwd: str) -> None:
    """Serve a line-oriented Architect chat over the existing WebSocket."""
    try:
        from openai import OpenAI
    except ImportError:
        await websocket.send_text("OpenAI SDK is not installed. Run the project setup first.\r\n")
        await websocket.close(code=1011)
        return

    if not os.environ.get("OPENAI_API_KEY"):
        await websocket.send_text("OPENAI_API_KEY is not configured.\r\n")
        await websocket.close(code=1011)
        return

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.environ.get("OPENAI_MODEL", "gpt-5.5")
    previous_response_id = None
    buffer = ""
    await websocket.send_text("\x1b[1;36mOpenAI Telco Architect\x1b[0m\r\nType a question and press Enter.\r\n\r\n> ")

    async def answer(prompt: str) -> None:
        nonlocal previous_response_id
        try:
            kwargs = {
                "model": model,
                "instructions": _instructions(cwd),
                "input": prompt,
                "max_output_tokens": int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "1800")),
                "store": True,
            }
            if previous_response_id:
                kwargs["previous_response_id"] = previous_response_id
            response = await asyncio.to_thread(client.responses.create, **kwargs)
            previous_response_id = response.id
            await websocket.send_text("\r\n\x1b[1;32mArchitect:\x1b[0m\r\n")
            await websocket.send_text(_response_text(response).replace("\n", "\r\n") + "\r\n\r\n> ")
        except Exception as exc:
            await websocket.send_text(f"\r\n\x1b[1;31mOpenAI request failed:\x1b[0m {exc}\r\n\r\n> ")

    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if "text" in msg:
                try:
                    obj = json.loads(msg["text"])
                    if isinstance(obj, dict) and obj.get("type") == "resize":
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass
                data = msg["text"]
            elif "bytes" in msg:
                data = msg["bytes"].decode("utf-8", errors="replace")
            else:
                continue
            for char in data:
                if char in ("\r", "\n"):
                    prompt = buffer.strip()
                    buffer = ""
                    if prompt:
                        await answer(prompt)
                    else:
                        await websocket.send_text("\r\n> ")
                elif char in ("\x08", "\x7f"):
                    if buffer:
                        buffer = buffer[:-1]
                        await websocket.send_text("\b \b")
                elif char.isprintable():
                    buffer += char
                    await websocket.send_text(char)
    except Exception:
        pass
