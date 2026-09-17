from __future__ import annotations

import asyncio
import fcntl
import json
import os
import pty
import shutil
import signal
import struct
import subprocess
import termios


class ClaudeBackend:
    provider = "claude"

    async def serve(self, websocket, cwd: str, model: str) -> None:
        command = shutil.which(os.environ.get("CLAUDE_COMMAND", "claude"))
        if not command:
            await websocket.send_text("Claude CLI not found in PATH.\r\n")
            await websocket.close(code=1011)
            return

        master_fd, slave_fd = pty.openpty()
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        args = [command]
        if model:
            args += ["--model", model]
        proc = subprocess.Popen(
            args, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            cwd=cwd, preexec_fn=os.setsid,
            env={**os.environ, "TERM": "xterm-256color", "CLAUDE_CODE_FORCE_SESSION_PERSISTENCE": "1"},
        )
        os.close(slave_fd)
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        loop = asyncio.get_event_loop()
        done = asyncio.Event()

        def on_readable():
            try:
                data = os.read(master_fd, 16384)
                if data:
                    asyncio.ensure_future(websocket.send_bytes(data))
                else:
                    done.set()
            except OSError:
                done.set()

        loop.add_reader(master_fd, on_readable)

        async def ws_to_pty():
            try:
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break
                    if "bytes" in msg:
                        os.write(master_fd, msg["bytes"])
                    elif "text" in msg:
                        try:
                            obj = json.loads(msg["text"])
                            if isinstance(obj, dict) and obj.get("type") == "resize":
                                rows = obj.get("rows") or 24
                                cols = obj.get("cols") or 80
                                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                                if proc.poll() is None:
                                    os.kill(proc.pid, signal.SIGWINCH)
                        except (json.JSONDecodeError, ValueError, OSError):
                            pass
            except Exception:
                pass
            finally:
                done.set()

        ws_task = asyncio.ensure_future(ws_to_pty())
        await done.wait()
        ws_task.cancel()
        loop.remove_reader(master_fd)
        try:
            os.close(master_fd)
        except OSError:
            pass
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
