"""Optional exclusive slot boundary for a complete background turn.

Disabled mode is deliberately an identity operation: it returns the original
async iterator, without allocating a lock, task, or changing scheduling.
Activation is intentionally not wired up until persistent prompting is ready.
"""
import asyncio
from collections.abc import AsyncIterator


def wrap(lines: AsyncIterator[str], *, enabled: bool = False,
         slot_lock: asyncio.Lock | None = None) -> AsyncIterator[str]:
    if not enabled:
        return lines
    if slot_lock is None:
        raise ValueError("Persistent turns require an explicit shared slot lock")
    return _exclusive(lines, slot_lock)


async def _exclusive(lines: AsyncIterator[str], lock: asyncio.Lock) -> AsyncIterator[str]:
    async with lock:
        try:
            async for line in lines:
                yield line
        finally:
            # Preserve generator cleanup while the slot is still exclusively held.
            await lines.aclose()
