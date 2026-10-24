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

    def install(
        self,
        *,
        coordinator: Any,
        lock: asyncio.Lock,
        capability: ContextCapability | None = None,
        backend_identity: str | None = None,
        server_id: int | None = None,
    ) -> SlotOwner:
        if self._owner is not None:
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

        self._owner = SlotOwner(
            lock=lock,
            coordinator=coordinator,
            capability=capability,
            backend_identity=backend_identity,
            server_id=server_id,
        )
        return self._owner

    def require(self) -> SlotOwner:
        if self._owner is None:
            raise SlotOwnerError("No verified inference-slot owner installed")
        return self._owner

    def clear(self) -> None:
        """Clear registration only; caller must first stop all active turns."""
        if self._owner is not None and self._owner.lock.locked():
            raise SlotOwnerError("Cannot clear owner while slot is locked")
        self._owner = None


slot_owners = SlotOwnerRegistry()
