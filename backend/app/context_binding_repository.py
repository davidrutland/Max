"""Database-backed ownership for persistent contexts; no inference or filesystem I/O.

The caller owns transaction boundaries. Snapshot filenames are basename-only and
uniquely allocated; this module does not claim the snapshot file already exists.
"""
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session

from app import models


class BindingError(RuntimeError):
    pass


@dataclass(frozen=True)
class BindingIdentity:
    backend_identity: str
    router_alias: str
    model_path: str
    model_fingerprint: str
    mmproj_path: str | None
    mmproj_fingerprint: str | None
    model_identity: str
    backend_build: str
    runtime_fingerprint: str
    effective_system_prompt: str
    tool_fingerprint: str


IDENTITY_FIELDS = tuple(BindingIdentity.__dataclass_fields__)

# Operational contract: a server ID and model name identify a stable model.
# Replacing the model or changing incompatible runtime settings under the
# same name requires clearing its saved contexts or assigning a new name.
COMPATIBILITY_FIELDS = (
    "backend_identity",
    "router_alias",
    "effective_system_prompt",
    "tool_fingerprint",
)


def _validate_identity(identity: BindingIdentity) -> None:
    if not isinstance(identity, BindingIdentity):
        raise BindingError("Invalid binding identity")
    for key in IDENTITY_FIELDS:
        value = getattr(identity, key)
        if key in ("mmproj_path", "mmproj_fingerprint"):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise BindingError(f"Invalid {key}")
        elif not isinstance(value, str) or not value.strip():
            raise BindingError(f"Missing {key}")
    from app.context_tool_identity import require_same_tools
    require_same_tools(identity.tool_fingerprint, identity.tool_fingerprint)
    if (identity.mmproj_path is None) != (identity.mmproj_fingerprint is None):
        raise BindingError("mmproj path and fingerprint must appear together")


def _owned_chat(db: Session, chat_id: int, user_id: int):
    if type(chat_id) is not int or type(user_id) is not int:
        raise BindingError("Invalid chat or user ID")
    chat = db.get(models.Chat, chat_id)
    if chat is None or chat.user_id != user_id:
        raise BindingError("Chat not found or not owned by user")
    return chat


def get_binding(db: Session, chat_id: int, user_id: int):
    _owned_chat(db, chat_id, user_id)
    return db.get(models.ChatContextBinding, chat_id)


def create_binding(db: Session, chat_id: int, user_id: int, identity: BindingIdentity):
    """Stage a new binding; caller must commit and handle uniqueness conflicts."""
    _owned_chat(db, chat_id, user_id)
    _validate_identity(identity)
    if db.get(models.ChatContextBinding, chat_id) is not None:
        raise BindingError("Binding already exists; identity is immutable")
    binding = models.ChatContextBinding(
        chat_id=chat_id,
        **{key: getattr(identity, key) for key in IDENTITY_FIELDS},
        snapshot_path=f"{uuid4().hex}.slot",
        snapshot_status="absent",
    )
    db.add(binding)
    return binding


def replace_binding(db: Session, chat_id: int, user_id: int, identity: BindingIdentity):
    """Explicitly replace a chat's configuration; invalidate its old KV snapshot.

    Keep the same chat and checkpoint filename. The authoritative history is
    unchanged; the next inference must evaluate it from an empty slot.
    """
    binding = get_binding(db, chat_id, user_id)
    if binding is None:
        raise BindingError("Binding does not exist")
    _validate_identity(identity)
    for key in IDENTITY_FIELDS:
        setattr(binding, key, getattr(identity, key))
    binding.snapshot_status = "absent"
    return binding


def assert_identity(binding: models.ChatContextBinding, identity: BindingIdentity) -> None:
    _validate_identity(identity)
    if binding is None or any(
        getattr(binding, key) != getattr(identity, key)
        for key in COMPATIBILITY_FIELDS
    ):
        raise BindingError("Binding identity differs; fork required")


def set_snapshot_status(db: Session, chat_id: int, user_id: int, status: str):
    """Stage snapshot metadata change, never an identity/path change."""
    binding = get_binding(db, chat_id, user_id)
    if binding is None:
        raise BindingError("Binding does not exist")
    if status not in ("absent", "ready", "uncertain"):
        raise BindingError("Invalid snapshot status")
    binding.snapshot_status = status
    return binding


def fork_binding(db: Session, source_chat_id: int, new_chat_id: int, user_id: int):
    """Allocate an independent fork slot; checkpoint copying happens separately."""
    source = get_binding(db, source_chat_id, user_id)
    if source is None:
        raise BindingError("Source binding does not exist")
    _owned_chat(db, new_chat_id, user_id)
    identity = BindingIdentity(**{key: getattr(source, key) for key in IDENTITY_FIELDS})
    return create_binding(db, new_chat_id, user_id, identity)


def confirm_fork_snapshot_copy(db: Session, source_chat_id: int, fork_chat_id: int,
                               user_id: int, *, fork_point_verified: bool):
    """Record successful independent copy of a checkpoint at the exact fork point.

    Caller must perform and verify file copy BEFORE invoking this method.
    This method does not copy files or verify the checkpoint's message boundary.
    """
    source = get_binding(db, source_chat_id, user_id)
    fork = get_binding(db, fork_chat_id, user_id)
    if source is None or fork is None or source_chat_id == fork_chat_id:
        raise BindingError("Missing or identical source/fork bindings")
    if fork_point_verified is not True:
        raise BindingError("Fork point not verified")
    if source.snapshot_status != "ready" or fork.snapshot_status != "absent":
        raise BindingError("Source must be ready and fork must be absent")
    if not source.snapshot_path or not fork.snapshot_path or source.snapshot_path == fork.snapshot_path:
        raise BindingError("Fork requires separate snapshot filenames")
    if any(getattr(source, key) != getattr(fork, key) for key in COMPATIBILITY_FIELDS):
        raise BindingError("Fork identity incompatible with source")
    fork.snapshot_status = "ready"
    return fork
