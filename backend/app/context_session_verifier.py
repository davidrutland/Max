"""Short-lived DB verifier callback for guarded_persistent_turn.

No DB session is held by the callback between invocations. The caller must
provide the effective identity and run the guard under the shared slot lock.
"""
from collections.abc import Callable
from typing import Any

from app.context_binding_verifier import verify_persisted_identity


def make_session_verifier(session_factory: Callable[[], Any], user_id: int):
    """Return verify_identity(chat_id, identity) for guarded_persistent_turn.

    No session is opened until verification runs. Failure propagates, and the
    session closes even when identity verification raises.
    """
    if not callable(session_factory):
        raise ValueError("A session factory is required")
    if type(user_id) is not int or user_id < 1:
        raise ValueError("A positive user ID is required")

    def verify_identity(chat_id, expected_identity):
        with session_factory() as db:
            return verify_persisted_identity(db, chat_id, user_id, expected_identity)

    return verify_identity
