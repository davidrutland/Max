"""Initialize and register a persistent conversation.

Caller must serialize this operation with inference using the shared slot lock.
No model operations, slot switching or persistence activation.
"""

import asyncio

from app.context_binding_initialization import ensure_turn_binding


class BindingRegistrationError(RuntimeError):
    pass


def initialize_and_register(
    *,
    session_factory,
    coordinator,
    slot_lock: asyncio.Lock,
    chat_id: int,
    user_id: int,
    base_identity,
    messages,
    tools_spec,
    allow_replace=False,
):
    """Commit a verified binding before registering it with the coordinator.

    Must be called while the shared slot lock is held. A registration failure
    leaves the committed binding available for a subsequent retry.
    """
    if not isinstance(slot_lock, asyncio.Lock) or not slot_lock.locked():
        raise BindingRegistrationError("Shared slot lock must be held")

    if not callable(session_factory):
        raise BindingRegistrationError("Session factory required")

    if not callable(getattr(coordinator, "register", None)):
        raise BindingRegistrationError("Coordinator registration required")

    key = str(chat_id)

    # Verify ownership and compatibility even for previously registered chats.
    with session_factory() as db:
        try:
            from app.context_binding_repository import get_binding, COMPATIBILITY_FIELDS
            from app.context_turn_identity import identity_for_turn
            old = get_binding(db, chat_id, user_id)
            expected = identity_for_turn(base_identity, messages, tools_spec)
            replaced = bool(old is not None and any(
                getattr(old, key) != getattr(expected, key) for key in COMPATIBILITY_FIELDS
            ))
            if replaced and not allow_replace:
                raise BindingRegistrationError("Configuration change: fork required unless Continue is confirmed")
            binding = ensure_turn_binding(
                db,
                chat_id=chat_id,
                user_id=user_id,
                base_identity=base_identity,
                messages=messages,
                tools_spec=tools_spec,
                allow_replace=replaced and allow_replace,
            )
            filename = binding.snapshot_path
            db.commit()
        except Exception:
            db.rollback()
            raise

    # A registered conversation must retain its original owner and filename.
    if key in coordinator.chat_ids:
        if (
            coordinator.chat_ids[key] != chat_id
            or coordinator.chat_users.get(key) != user_id
            or coordinator.orchestrator.contexts[key].filename != filename
        ):
            raise BindingRegistrationError(
                "Existing coordinator registration differs from binding"
            )
        return replaced

    coordinator.register(chat_id, user_id=user_id)
    return replaced
