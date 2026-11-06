"""Process-local inference-slot ownership; not connected to live chat routes.

A slot owner is installed explicitly only after backend compatibility is verified.
No database session is created or retained by this registry.
"""
import asyncio
from dataclasses import dataclass
from typing import Any

from app.context_capabilities import ContextCapability


class SlotOwnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SlotOwner:
    lock: asyncio.Lock
    coordinator: Any
    capability: ContextCapability | None = None
    backend_identity: str | None = None
    server_id: int | None = None


class SlotOwnerRegistry:
    """Single-process registry; multi-worker deployment is unsupported."""

    def __init__(self):
        self._owner: SlotOwner | None = None
        self._by_server: dict[int, SlotOwner] = {}

    def install(
        self,
        *,
        coordinator: Any,
        lock: asyncio.Lock,
        capability: ContextCapability | None = None,
        backend_identity: str | None = None,
        server_id: int | None = None,
    ) -> SlotOwner:
        if server_id is not None and server_id in self._by_server:
            raise SlotOwnerError("Inference-slot owner already installed for server")
        if self._owner is not None and server_id is None:
            raise SlotOwnerError("Inference-slot owner already installed")
        if not isinstance(lock, asyncio.Lock):
            raise SlotOwnerError("A shared asyncio.Lock is required")
        if coordinator is None or not callable(getattr(coordinator, "switch", None)) or not callable(getattr(coordinator, "mark_dirty", None)):
            raise SlotOwnerError("A context coordinator is required")
        if capability is not None:
            if not isinstance(capability, ContextCapability) or capability.supported is not True:
                raise SlotOwnerError("Verified context capability required")
            if not isinstance(backend_identity, str) or not backend_identity.strip():
                raise SlotOwnerError("Configured backend identity required")
        elif backend_identity is not None:
            raise SlotOwnerError("Backend identity requires verified capability")

        owner = SlotOwner(
            lock=lock,
            coordinator=coordinator,
            capability=capability,
            backend_identity=backend_identity,
            server_id=server_id,
        )
        if server_id is not None:
            self._by_server[server_id] = owner
        if self._owner is None:
            self._owner = owner
        return owner

    def require_for_server(self, server_id: int) -> SlotOwner:
        try:
            return self._by_server[server_id]
        except KeyError as exc:
            raise SlotOwnerError("No inference-slot owner for server") from exc

    def require_for_backend_identity(self, identity: str) -> SlotOwner:
        matches = [owner for owner in self._by_server.values() if owner.backend_identity == identity]
        if len(matches) != 1:
            raise SlotOwnerError("No unique inference-slot owner for backend identity")
        return matches[0]

    def require(self) -> SlotOwner:
        if self._owner is None:
            raise SlotOwnerError("No verified inference-slot owner installed")
        return self._owner

    def clear(self) -> None:
        """Clear registration only; caller must first stop all active turns."""
        if any(owner.lock.locked() for owner in self._by_server.values()) or (self._owner is not None and self._owner.lock.locked()):
            raise SlotOwnerError("Cannot clear owner while slot is locked")
        self._owner = None
        self._by_server.clear()


slot_owners = SlotOwnerRegistry()
