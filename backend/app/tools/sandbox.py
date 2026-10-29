"""Sandbox tools backed by the OpenHands agent-server HTTP API."""

import asyncio
import base64
import secrets
import shlex
from pathlib import Path

import os
import httpx

from app import config
from app.tools.registry import Tool, registry, ERROR_PREFIX


BASE_URL = config.SANDBOX_BASE_URL.rstrip("/")
WORKSPACE = Path("/workspace")
_conversation_id: str | None = None
_conversation_lock = asyncio.Lock()


def _path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path is required")

    path = Path(value)
    if not path.is_absolute():
        path = WORKSPACE / path

    path = Path(os.path.normpath(str(path)))
    if path != WORKSPACE and WORKSPACE not in path.parents:
        raise ValueError("path must be inside /workspace")
    return str(path)


async def _conversation() -> str:
    global _conversation_id

    if _conversation_id is not None:
        return _conversation_id

    async with _conversation_lock:
        if _conversation_id is not None:
            return _conversation_id

        payload = {
            "workspace": {
                "working_dir": str(WORKSPACE),
                "kind": "LocalWorkspace",
            },
            "agent": {
                "llm": {
                    "model": "sandbox",
                    "api_key": "sandbox",
                    "usage_id": "sandbox",
                },
                "tools": [{"name": "terminal", "params": {}}],
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{BASE_URL}/api/conversations",
                    json=payload,
                )
                response.raise_for_status()
                _conversation_id = response.json()["id"]
        except Exception as exc:
            raise RuntimeError("could not create sandbox conversation") from exc

        return _conversation_id


async def _exec(command: str, cwd: str, timeout: int) -> str:
    cid = await _conversation()

    try:
        async with httpx.AsyncClient(timeout=timeout + 15) as client:
            response = await client.post(
                f"{BASE_URL}/api/conversations/{cid}/bash/execute_bash_command",
                json={
                    "command": command,
                    "cwd": cwd,
                    "timeout": timeout,
                },
            )
            response.raise_for_status()
            result = response.json()
    except Exception:
        return f"{ERROR_PREFIX} sandbox command failed."

    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    exit_code = result.get("exit_code")

    parts = [f"exit_code={exit_code}"]
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    return "\n".join(parts)


async def _sandbox_exec(args: dict) -> str:
    command = (args.get("command") or "").strip()
    if not command:
        return f"{ERROR_PREFIX} command is required."

    try:
        cwd = _path(args.get("cwd", str(WORKSPACE)))
        timeout = int(args.get("timeout", 300))
    except (TypeError, ValueError) as exc:
        return f"{ERROR_PREFIX} invalid sandbox arguments: {exc}"

    if not 1 <= timeout <= 300:
        return f"{ERROR_PREFIX} timeout must be between 1 and 300 seconds."

    return await _exec(command, cwd, timeout)


async def _sandbox_edit(args: dict) -> str:
    try:
        path = _path(args.get("path", ""))
    except ValueError as exc:
        return f"{ERROR_PREFIX} {exc}"

    old = args.get("old")
    new = args.get("new")

    if not isinstance(old, str) or not old:
        return f"{ERROR_PREFIX} old text is required."
    if not isinstance(new, str):
        return f"{ERROR_PREFIX} new text is required."

    try:
        cid = await _conversation()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BASE_URL}/api/conversations/{cid}/file/download",
                params={"path": path},
            )
            response.raise_for_status()
            content = response.content.decode("utf-8", errors="replace")

            replace_all = bool(args.get("replace_all", False))
            count = content.count(old)

            if count == 0:
                return f"{ERROR_PREFIX} old text was not found in {path}."
            if not replace_all and count != 1:
                return f"{ERROR_PREFIX} old text occurs {count} times; set replace_all=true to replace all occurrences."

            updated = content.replace(old, new, -1 if replace_all else 1)

            response = await client.post(
                f"{BASE_URL}/api/conversations/{cid}/file/upload",
                params={"path": path},
                files={
                    "file": (
                        Path(path).name,
                        updated.encode("utf-8"),
                        "text/plain; charset=utf-8",
                    )
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return f"{ERROR_PREFIX} sandbox edit failed (HTTP {exc.response.status_code})."
    except Exception:
        return f"{ERROR_PREFIX} sandbox edit failed."

    return f"Edited {path}"


async def _sandbox_write(args: dict) -> str:
    try:
        path = _path(args.get("path", ""))
    except ValueError as exc:
        return f"{ERROR_PREFIX} {exc}"

    if "content" not in args or not isinstance(args["content"], str):
        return f"{ERROR_PREFIX} content is required."

    cid = await _conversation()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{BASE_URL}/api/conversations/{cid}/file/upload",
                params={"path": path},
                files={
                    "file": (
                        Path(path).name,
                        args["content"].encode("utf-8"),
                        "text/plain; charset=utf-8",
                    )
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return f"{ERROR_PREFIX} sandbox write failed (HTTP {exc.response.status_code})."
    except Exception:
        return f"{ERROR_PREFIX} sandbox write failed."

    return f"Wrote {path}"


async def _sandbox_read(args: dict) -> str:
    try:
        path = _path(args.get("path", ""))
    except ValueError as exc:
        return f"{ERROR_PREFIX} {exc}"

    cid = await _conversation()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{BASE_URL}/api/conversations/{cid}/file/download",
                params={"path": path},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return f"{ERROR_PREFIX} sandbox read failed (HTTP {exc.response.status_code})."
    except Exception:
        return f"{ERROR_PREFIX} sandbox read failed."

    return response.content.decode("utf-8", errors="replace")


async def _sandbox_ls(args: dict) -> str:
    try:
        path = _path(args.get("path", str(WORKSPACE)))
    except ValueError as exc:
        return f"{ERROR_PREFIX} {exc}"

    return await _exec(f"ls -la -- {shlex.quote(path)}", str(WORKSPACE), 30)


registry.register(
    Tool(
        name="sandbox_exec",
        description="Execute a shell command inside the isolated sandbox. The working directory must be inside /workspace.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {
                    "type": "string",
                    "description": "Working directory inside /workspace. Defaults to /workspace.",
                },
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 300,
                    "description": "Maximum execution time in seconds. Defaults to 300.",
                },
            },
            "required": ["command"],
        },
        handler=_sandbox_exec,
        source="sandbox",
        mutating=False,
    )
)

registry.register(
    Tool(
        name="sandbox_edit",
        description="Replace text in a text file inside the isolated sandbox workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path inside /workspace.",
                },
                "old": {
                    "type": "string",
                    "description": "Existing text to replace.",
                },
                "new": {
                    "type": "string",
                    "description": "Replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace every occurrence instead of requiring exactly one.",
                },
            },
            "required": ["path", "old", "new"],
        },
        handler=_sandbox_edit,
        source="sandbox",
        mutating=False,
    )
)

registry.register(
    Tool(
        name="sandbox_write",
        description="Write a text file inside the isolated sandbox workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path inside /workspace.",
                },
                "content": {
                    "type": "string",
                    "description": "Complete text content to write.",
                },
            },
            "required": ["path", "content"],
        },
        handler=_sandbox_write,
        source="sandbox",
        mutating=False,
    )
)

registry.register(
    Tool(
        name="sandbox_read",
        description="Read a text file inside the isolated sandbox workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path inside /workspace.",
                }
            },
            "required": ["path"],
        },
        handler=_sandbox_read,
        source="sandbox",
        mutating=False,
    )
)

registry.register(
    Tool(
        name="sandbox_ls",
        description="List files in a directory inside the isolated sandbox workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory inside /workspace. Defaults to /workspace.",
                }
            },
        },
        handler=_sandbox_ls,
        source="sandbox",
        mutating=False,
    )
)


# Executed inside OpenHands, where /workspace is actually mounted. Resolve each
# component using O_NOFOLLOW and copy from the verified descriptor, not a path.
_SNAPSHOT_SCRIPT = r"""
import os, sys, stat
parts = sys.argv[1].split('/')
name = sys.argv[2]
root = os.open('/workspace', os.O_RDONLY | os.O_DIRECTORY)
fd = root
try:
    for index, part in enumerate(parts):
        if not part or part in ('.', '..'):
            raise ValueError('invalid path component')
        next_fd = os.open(part, os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if index < len(parts) - 1 else os.O_NONBLOCK), dir_fd=fd)
        if fd != root:
            os.close(fd)
        fd = next_fd
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        raise ValueError('not a regular file')
    if st.st_size > 100 * 1024 * 1024:
        raise ValueError('attachment exceeds size limit')
    target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
    try:
        count = 0
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block: break
            count += len(block)
            if count > 100 * 1024 * 1024: raise ValueError('attachment exceeds size limit')
            os.write(target, block)
    finally:
        os.close(target)
except Exception:
    try: os.unlink(name, dir_fd=root)
    except OSError: pass
    raise
finally:
    if fd != root: os.close(fd)
    os.close(root)
"""



async def fetch_attachment(path: str) -> bytes:
    """Download a no-symlink snapshot made inside the OpenHands workspace."""
    path = _path(path)
    relative = str(Path(path).relative_to(WORKSPACE))
    if relative == '.':
        raise ValueError('attachment must be a regular file')
    snapshot = '.max-attachment-' + secrets.token_hex(20)
    script = base64.b64encode(_SNAPSHOT_SCRIPT.encode()).decode()
    command = (
        'python3 -c ' + shlex.quote('import base64; exec(base64.b64decode(' + repr(script) + '))')
        + ' ' + shlex.quote(relative) + ' ' + shlex.quote(snapshot)
    )
    result = await _exec(command, str(WORKSPACE), 45)
    if not result.startswith('exit_code=0'):
        raise ValueError('could not securely snapshot attachment: ' + result[:300])
    cid = await _conversation()
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream('GET', f'{BASE_URL}/api/conversations/{cid}/file/download', params={'path': str(WORKSPACE / snapshot)}) as response:
                response.raise_for_status()
                chunks, total = [], 0
                from app.artifact_store import MAX_BYTES
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError('attachment exceeds size limit')
                    chunks.append(chunk)
                return b''.join(chunks)
    finally:
        await _exec('rm -f -- ' + shlex.quote(str(WORKSPACE / snapshot)), str(WORKSPACE), 15)


async def _sandbox_attach(args: dict) -> str:
    try:
        return _path(args.get("path", ""))
    except ValueError as exc:
        return f"{ERROR_PREFIX} {exc}"


registry.register(Tool(
    name="sandbox_attach",
    description="Attach an existing file from /workspace to this chat. Max automatically shows an Open control with Preview and Download; do not invent or include a separate download URL in your reply. Simply say the file is attached.",
    parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    handler=_sandbox_attach, source="sandbox", mutating=False,
))
