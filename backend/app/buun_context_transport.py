"""Explicit Buun persistence transport selection, independent of model identity.

This module does not detect topology, load models, or change persistence settings.
"""

from dataclasses import dataclass
from enum import Enum

from app.buun_context_adapter import BuunContextAdapter, BuunContextError, SlotTransferResult


class TransportMode(str, Enum):
    DIRECT = "direct"
    ROUTER = "router"


@dataclass(frozen=True)
class BuunTransport:
    mode: TransportMode
    url: str
    alias: str | None = None

    def __post_init__(self):
        if not isinstance(self.mode, TransportMode):
            raise BuunContextError("Transport mode must be 'direct' or 'router'")
        if not isinstance(self.url, str) or not self.url.strip():
            raise BuunContextError("Missing transport URL")
        if self.mode is TransportMode.ROUTER:
            if not isinstance(self.alias, str) or not self.alias.strip():
                raise BuunContextError("Router transport requires a model alias")
        elif self.alias is not None:
            raise BuunContextError("Direct transport must not specify a router alias")


class BuunContextTransport:
    """Dispatches slot operations to the already-tested HTTP adapter."""

    def __init__(self, adapter: BuunContextAdapter, target: BuunTransport):
        self.adapter = adapter
        self.target = target

    async def save(self, slot_id: int, filename: str) -> SlotTransferResult:
        if self.target.mode is TransportMode.ROUTER:
            return await self.adapter.save_via_router(
                self.target.url, self.target.alias, slot_id, filename
            )
        return await self.adapter.save_slot(self.target.url, slot_id, filename)

    async def restore(self, slot_id: int, filename: str) -> SlotTransferResult:
        if self.target.mode is TransportMode.ROUTER:
            return await self.adapter.restore_via_router(
                self.target.url, self.target.alias, slot_id, filename
            )
        return await self.adapter.restore_slot(self.target.url, slot_id, filename)

    async def erase(self, slot_id: int) -> int:
        if self.target.mode is TransportMode.ROUTER:
            return await self.adapter.erase_via_router(
                self.target.url, self.target.alias, slot_id
            )
        return await self.adapter.erase_slot(self.target.url, slot_id)
