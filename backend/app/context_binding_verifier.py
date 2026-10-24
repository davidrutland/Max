"""Read-only persisted identity verification before any slot operation.

An absent *binding* is not an absent *snapshot*: first-time persistent chats
must have a separately created, immutable binding before reaching this guard.
"""
from sqlalchemy.orm import Session

from app.context_binding_repository import (
    BindingError, BindingIdentity, assert_identity, get_binding,
)


class ContextBindingVerificationError(RuntimeError):
    pass


def verify_persisted_identity(db: Session, chat_id: int, user_id: int,
                              expected_identity: BindingIdentity) -> bool:
    """Return literal True only for an owned, compatible, usable binding.

    Does not create bindings, mutate status, commit, or access snapshots.
    The caller must run this under the shared slot lock, before switching.
    """
    try:
        binding = get_binding(db, chat_id, user_id)
        if binding is None:
            raise ContextBindingVerificationError(
                "No persisted binding; first-time binding creation required"
            )
        assert_identity(binding, expected_identity)
        if binding.snapshot_status not in ("absent", "ready"):
            raise ContextBindingVerificationError("Snapshot state requires recovery")
        if not binding.snapshot_path:
            raise ContextBindingVerificationError("Snapshot filename missing")
    except BindingError as exc:
        raise ContextBindingVerificationError(str(exc)) from exc
    return True
