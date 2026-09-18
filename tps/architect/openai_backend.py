from __future__ import annotations

import asyncio
import json
import os

from tps.architect.context import instructions
from tps.architect.base import PromptHook, ResponseHook


def response_text(response) -> str:
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


class OpenAIBackend:
    provider = "openai"

    async def serve(self, websocket, cwd: str, model: str,
                    on_prompt: PromptHook | None = None,
                    on_response: ResponseHook | None = None) -> None:
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
        previous_response_id = None
        await websocket.send_text(
            f"\x1b[1;36mOpenAI Telco Architect ({model})\x1b[0m\r\n"
            "Type a question and press Enter.\r\n\r\n> "
        )

        async def answer(prompt: str) -> None:
            nonlocal previous_response_id
            try:
                kwargs = {
                    "model": model,
                    "instructions": instructions(cwd, "OpenAI"),
                    "input": await on_prompt(prompt) if on_prompt else prompt,
                    "max_output_tokens": int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "1800")),
                    "store": True,
                }
                if previous_response_id:
                    kwargs["previous_response_id"] = previous_response_id
                response = await asyncio.to_thread(client.responses.create, **kwargs)
                previous_response_id = response.id
                text = response_text(response)
                if on_response:
                    await on_response(text)
                await websocket.send_text("\r\n\x1b[1;32mArchitect:\x1b[0m\r\n")
                await websocket.send_text(text.replace("\n", "\r\n") + "\r\n\r\n> ")
            except Exception as exc:
                await websocket.send_text(f"\r\n\x1b[1;31mOpenAI request failed:\x1b[0m {exc}\r\n\r\n> ")

        await _serve_line_input(websocket, answer)


async def _serve_line_input(websocket, answer) -> None:
    buffer = ""
    while True:
        msg = await websocket.receive()
        if msg.get("type") == "websocket.disconnect":
            return
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
