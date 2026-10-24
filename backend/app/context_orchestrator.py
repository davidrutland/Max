"""In-memory, single-slot context lifecycle coordinator.

No DB writes, model loading, or capability activation. Caller supplies unique
snapshot filenames and persists snapshot metadata separately in later patches.
Do not share one coordinator across independently running model processes.
"""

import asyncio
from dataclasses import dataclass
from typing import Protocol


class ContextSwitchError(RuntimeError):
    """The requested switch did not complete safely."""


class SlotTransport(Protocol):
    async def save(self, slot_id: int, filename: str): ...
    async def restore(self, slot_id: int, filename: str): ...
    async def erase(self, slot_id: int): ...


@dataclass
class ConversationContext:
    filename: str
    has_snapshot: bool = False


class ContextOrchestrator:
    """Coordinates one live slot. Not yet safe for multiple backend workers."""

    def __init__(self, transport: SlotTransport, slot_id: int = 0):
        if type(slot_id) is not int or slot_id < 0:
            raise ValueError("Invalid slot ID")
        self.transport = transport
        self.slot_id = slot_id
        self.contexts: dict[str, ConversationContext] = {}
        self.active_chat: str | None = None
        self.dirty = False
        self._lock = asyncio.Lock()
        self.uncertain = False

    def register(self, chat_id: str, filename: str, *, has_snapshot: bool = False):
        if not chat_id or not filename or not isinstance(chat_id, str) or not isinstance(filename, str):
            raise ValueError("Chat ID and filename required")
        if chat_id in self.contexts:
            raise ValueError("Chat already registered")
        if any(ctx.filename == filename for ctx in self.contexts.values()):
            raise ValueError("Snapshot filename already assigned")
        self.contexts[chat_id] = ConversationContext(filename, has_snapshot)

    def mark_dirty(self, chat_id: str):
        if self.uncertain or self.active_chat != chat_id:
            raise ContextSwitchError("Chat does not own a verified active slot")
        self.dirty = True

    def release_active(self):
        """Release saved slot ownership without touching Buun or snapshots."""
        if self.uncertain:
            raise ContextSwitchError("Slot state uncertain; recovery required")
        if self.dirty:
            raise ContextSwitchError("Active context must be saved before release")
        self.active_chat = None

    async def save_active(self):
        """Persist the dirty active slot without changing its owner."""
        async with self._lock:
            if self.uncertain:
                raise ContextSwitchError("Slot state uncertain; recovery required")
            if self.active_chat is None or not self.dirty:
                return
            source = self.contexts[self.active_chat]
            try:
                await self.transport.save(self.slot_id, source.filename)
            except Exception as exc:
                # A failed checkpoint does not change the live slot. Keep it
                # dirty so the next checkpoint/switch can retry.
                raise ContextSwitchError("Checkpoint save failed; live context retained") from exc
            source.has_snapshot = True
            self.dirty = False

    async def switch(self, chat_id: str):
        """Save source, clear slot, restore target, then commit ownership.

        Caller must serialize inference against this operation externally.
        """
        async with self._lock:
            if self.uncertain:
                raise ContextSwitchError("Slot state uncertain; recovery required")
            if chat_id not in self.contexts:
                raise ContextSwitchError("Unknown conversation")
            if self.active_chat == chat_id:
                return

            if self.active_chat is not None and self.dirty:
                source = self.contexts[self.active_chat]
                try:
                    await self.transport.save(self.slot_id, source.filename)
                except Exception as exc:
                    # Save failure does not alter slot ownership or RAM state.
                    # Retain the live conversation and retry on a later switch.
                    # Only erase/restore failures make the slot uncertain.
                    raise ContextSwitchError("Save failed; live context retained; switch blocked") from exc
                source.has_snapshot = True
                self.dirty = False

            # Do not claim any active owner after attempting to replace the slot.
            self.active_chat = None
            try:
                await self.transport.erase(self.slot_id)
                target = self.contexts[chat_id]
                if target.has_snapshot:
                    await self.transport.restore(self.slot_id, target.filename)
            except Exception as exc:
                self.uncertain = True
                raise ContextSwitchError("Slot replacement failed; recovery required") from exc

            self.active_chat = chat_id
            self.dirty = False

    def reset_after_external_recovery(self):
        """Caller must first independently verify or clear the real slot."""
        self.active_chat = None
        self.dirty = False
        self.uncertain = False
