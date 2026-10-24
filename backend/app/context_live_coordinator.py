"""Single-process context switching with durable snapshot metadata.

Not wired into chat routes. Caller must serialize inference for the entire turn,
not merely while calling switch(), and verify model/prompt compatibility first.
"""
from pathlib import Path
import os
from uuid import uuid4
import stat
from contextlib import contextmanager, nullcontext
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.context_binding_repository import get_binding, set_snapshot_status
from app.context_orchestrator import ContextOrchestrator, ContextSwitchError
from app.context_snapshot_files import SnapshotFileStore


class LiveContextError(RuntimeError):
    pass


def _verified_file(store: SnapshotFileStore, filename: str) -> bool:
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        return False
    try:
        info = (store.directory / filename).lstat()
        return stat.S_ISREG(info.st_mode) and info.st_size > 0
    except FileNotFoundError:
        return False


@contextmanager
def _session_scope(db_or_factory):
    """A factory gives each operation its own session; a Session preserves legacy API."""
    if isinstance(db_or_factory, Session):
        with nullcontext(db_or_factory) as db:
            yield db
    else:
        db = db_or_factory()
        try:
            yield db
        finally:
            db.close()


class _VerifiedTransport:
    """Commit source readiness before the orchestrator may erase the slot."""

    def __init__(self, transport, db_or_factory, store: SnapshotFileStore,
                 chat_ids: dict[str, int], chat_users: dict[str, int]):
        self.transport = transport
        self.db_or_factory = db_or_factory
        self.store = store
        self.chat_ids = chat_ids
        self.chat_users = chat_users
        self.source_chat: str | None = None

    async def save(self, slot_id: int, filename: str):
        """Write a complete checkpoint before replacing the last good one.

        Buun writes to the named file directly. Never give it the committed
        filename: an interrupted save must not destroy restart recovery.
        """
        if self.source_chat is None:
            raise LiveContextError("No source owner for save")
        if Path(filename).name != filename or filename in ("", ".", ".."):
            raise LiveContextError("Unsafe snapshot filename")
        staged = f"stage-{uuid4().hex}.slot"
        try:
            result = await self.transport.save(slot_id, staged)
            if not _verified_file(self.store, staged):
                raise LiveContextError("Saved snapshot missing or empty")
            os.replace(self.store.directory / staged, self.store.directory / filename)
            directory_fd = os.open(self.store.directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            with _session_scope(self.db_or_factory) as db:
                try:
                    set_snapshot_status(
                        db,
                        self.chat_ids[self.source_chat],
                        self.chat_users[self.source_chat],
                        "ready",
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
            return result
        finally:
            # A failed/partial save cannot be mistaken for a committed snapshot.
            (self.store.directory / staged).unlink(missing_ok=True)

    async def restore(self, slot_id: int, filename: str):
        if not _verified_file(self.store, filename):
            raise LiveContextError("Destination snapshot missing or empty")
        return await self.transport.restore(slot_id, filename)

    async def erase(self, slot_id: int):
        return await self.transport.erase(slot_id)


class LiveContextCoordinator:
    """Owns one orchestrator and DB session for a single inference slot.

    This object is NOT safe for multi-worker use. Register bindings only after
    independently verifying backend/model/runtime/system-prompt compatibility.
    """

    def __init__(self, db: Session | Callable[[], Session], user_id: int,
                 store: SnapshotFileStore, transport, slot_id: int = 0):
        # A session factory is required for a process-lived coordinator. Passing
        # a Session remains supported for existing isolated callers/tests.
        if not isinstance(db, Session) and not callable(db):
            raise TypeError("Expected a SQLAlchemy Session or session factory")
        self.db_or_factory = db
        self.user_id = user_id
        self.chat_users: dict[str, int] = {}
        self.store = store
        self.chat_ids: dict[str, int] = {}
        self._transport = _VerifiedTransport(transport, db, store, self.chat_ids, self.chat_users)
        self.orchestrator = ContextOrchestrator(self._transport, slot_id)
        self._turns_since_checkpoint = 0

    def register(self, chat_id: int, *, user_id: int | None = None):
        owner_id = self.user_id if user_id is None else user_id
        with _session_scope(self.db_or_factory) as db:
            binding = get_binding(db, chat_id, owner_id)
            if binding is None or not binding.snapshot_path:
                raise LiveContextError("Missing snapshot binding")
            if binding.snapshot_status not in ("ready", "absent"):
                raise LiveContextError("Snapshot state requires recovery")
            key = str(chat_id)
            if key in self.chat_ids:
                raise LiveContextError("Chat already registered")
            filename = binding.snapshot_path
            ready = binding.snapshot_status == "ready"
        if ready and not _verified_file(self.store, filename):
            raise LiveContextError("Ready snapshot missing or empty")
        self.orchestrator.register(key, filename, has_snapshot=ready)
        self.chat_ids[key] = chat_id
        self.chat_users[key] = owner_id

    def invalidate_registered_snapshot(self, chat_id: int) -> bool:
        """Mirror a committed DB invalidation, if this chat is registered.

        Inactive conversations need not be registered in this process. Never
        touch another conversation's live slot or create a phantom context.
        Caller holds the shared inference lock.
        """
        ctx = self.orchestrator.contexts.get(str(chat_id))
        if ctx is None:
            return False
        ctx.has_snapshot = False
        return True

    async def discard_replaced_context(self, chat_id: int):
        """Discard stale RAM/KV state after an explicitly confirmed rebind.

        Caller holds the shared inference lock. A different active chat is
        preserved by the normal subsequent switch; no model is loaded here.
        """
        key = str(chat_id)
        async with self.orchestrator._lock:
            ctx = self.orchestrator.contexts[key]
            ctx.has_snapshot = False
            if self.orchestrator.active_chat == key:
                self.orchestrator.active_chat = None
                self.orchestrator.dirty = False
                try:
                    await self.orchestrator.transport.erase(self.orchestrator.slot_id)
                except Exception:
                    self.orchestrator.uncertain = True
                    raise

    def mark_dirty(self, chat_id: int):
        self.orchestrator.mark_dirty(str(chat_id))

    async def completed_turn(self, chat_id: int, interval: int):
        """Checkpoint completed turns without evicting the live slot."""
        if interval < 1:
            raise ValueError("Snapshot interval must be positive")
        if self.active_chat_id != chat_id:
            raise LiveContextError("Completed turn does not own the live slot")
        self._turns_since_checkpoint += 1
        if self._turns_since_checkpoint >= interval:
            try:
                await self.save_active()
            except ContextSwitchError:
                # Periodic checkpoints are best-effort: never fail an otherwise
                # successful inference turn or poison the RAM-resident slot.
                # Keep the counter due so the next completed turn retries.
                return
            self._turns_since_checkpoint = 0

    async def switch_model(self, chat_id: int, load_model):
        """Activate a chat on its bound model; caller owns the shared slot lock.

        The model transition and snapshot restore are one indivisible operation
        from the application's point of view. Never restore into the wrong worker.
        """
        from app.context_model_transition import transition_model

        key = str(chat_id)
        if key not in self.chat_ids:
            raise LiveContextError("Unregistered conversation")
        with _session_scope(self.db_or_factory) as db:
            binding = get_binding(db, chat_id, self.chat_users[key])
            if binding is None or not binding.router_alias:
                raise LiveContextError("Conversation model binding missing")
            model = binding.router_alias
        await transition_model(self, model, load_model)
        await self.switch(chat_id)

    async def switch(self, chat_id: int):
        key = str(chat_id)
        if key not in self.chat_ids:
            raise LiveContextError("Unregistered conversation")
        previous = self.orchestrator.active_chat
        self._transport.source_chat = previous
        try:
            await self.orchestrator.switch(key)
            if previous != key:
                self._turns_since_checkpoint = 0
        except Exception:
            # Transport save manages its own transaction. No process-lived
            # session remains to roll back when using a session factory.
            raise
        finally:
            self._transport.source_chat = None

    async def save_active(self):
        self._transport.source_chat = self.orchestrator.active_chat
        try:
            await self.orchestrator.save_active()
        finally:
            self._transport.source_chat = None

    @property
    def active_chat_id(self) -> int | None:
        active = self.orchestrator.active_chat
        return self.chat_ids[active] if active is not None else None
