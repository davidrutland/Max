"""Process-wide Buun persistence owner. Single worker only."""

import asyncio
import os
from contextlib import asynccontextmanager

import httpx

from app import config
from app.buun_context_adapter import BuunContextAdapter
from app.buun_context_transport import BuunContextTransport, BuunTransport, TransportMode
from app.context_capabilities import ContextCapability
from app.context_live_coordinator import LiveContextCoordinator
from app.context_slot_owner import slot_owners
from app.context_snapshot_files import SnapshotFileStore
from app.database import SessionLocal


def required_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for Buun persistence")
    return value


@asynccontextmanager
async def context_owner_lifespan():
    if config.CONTEXT_PERSISTENCE_MODE == "disabled":
        yield
        return

    if config.CONTEXT_PERSISTENCE_MODE != "auto":
        raise RuntimeError("Unsupported persistence mode")

    url = required_setting("BUUN_CONTEXT_URL")
    alias = required_setting("BUUN_CONTEXT_MODEL")
    directory = required_setting("BUUN_SLOT_SAVE_PATH")
    identity = required_setting("BUUN_BACKEND_IDENTITY")
    try:
        server_id = int(required_setting("BUUN_CONTEXT_SERVER_ID"))
    except ValueError as exc:
        raise RuntimeError("BUUN_CONTEXT_SERVER_ID must be an integer") from exc
    if server_id <= 0:
        raise RuntimeError("BUUN_CONTEXT_SERVER_ID must be positive")

    store = SnapshotFileStore(directory)
    target = BuunTransport(TransportMode.ROUTER, url, alias=alias)

    async with httpx.AsyncClient() as client:
        transport = BuunContextTransport(BuunContextAdapter(client), target)
        coordinator = LiveContextCoordinator(
            SessionLocal, 0, store, transport, slot_id=0
        )
        lock = asyncio.Lock()

        # This explicit configuration represents the previously verified
        # Buun save/restore/erase implementation, not an HTTP capability probe.
        capability = ContextCapability(
            supported=True,
            backend="buun",
            reason="Explicitly configured verified Buun router",
        )

        slot_owners.install(
            coordinator=coordinator,
            lock=lock,
            capability=capability,
            backend_identity=identity,
            server_id=server_id,
        )
        try:
            yield
        finally:
            slot_owners.clear()
