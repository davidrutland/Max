"""Opt-in persistent turn lifecycle; not connected to routes or capability detection.

Caller must complete capability/identity preflight and provide a shared slot lock.
The lock covers switch, the entire agentic iterator, and generator cleanup.
"""
import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from app.context_turn_boundary import wrap


class Coordinator(Protocol):
    async def switch(self, chat_id: int): ...
    def mark_dirty(self, chat_id: int): ...


async def _run(lines: AsyncIterator[str], coordinator: Coordinator,
               chat_id: int) -> AsyncIterator[str]:
    # Executed only once the shared slot lock is held by wrap().
    await coordinator.switch(chat_id)
    try:
        # Mark dirty before the first possible inference call. A cancelled or
        # failed request may have mutated the KV cache without yielding a line.
        coordinator.mark_dirty(chat_id)
        async for line in lines:
            yield line
    finally:
        # Keep cleanup inside the exclusive region, including cancellation.
        await lines.aclose()


def persistent_turn(lines: AsyncIterator[str], *, coordinator: Coordinator,
                    chat_id: int, slot_lock: asyncio.Lock) -> AsyncIterator[str]:
    """Build an opt-in iterator. Does not activate persistence itself.

    The caller is responsible for verified capability and identity preflight,
    as well as holding the same slot_lock across all chats sharing this slot.
    """
    if slot_lock is None:
        raise ValueError("A shared slot lock is required")
    if type(chat_id) is not int or chat_id < 1:
        raise ValueError("A positive chat ID is required")
    return wrap(_run(lines, coordinator, chat_id), enabled=True,
                slot_lock=slot_lock)
