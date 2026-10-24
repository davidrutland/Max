"""Connect turn binding verification to the guarded persistent lifecycle.

Database sessions are opened only for verification and closed before
slot switching or inference. No route wiring or persistence activation.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.context_binding_repository import BindingIdentity
from app.context_pre_switch_guard import guarded_persistent_turn
from app.context_turn_verification import verify_turn_binding


async def verified_persistent_turn(
    lines: AsyncIterator[str],
    *,
    chat_id: int,
    user_id: int,
    capability: Any,
    slot_lock: asyncio.Lock,
    coordinator: Any,
    session_factory: Callable,
    base_identity: BindingIdentity,
    messages: list[dict],
    tools_spec: Any,
) -> AsyncIterator[str]:
    """Verify under the slot lock using a short-lived database session.

    The session closes before the coordinator switches or inference starts.
    The factory must return a synchronous context manager supporting
    __enter__ and __exit__.
    """
    if not callable(session_factory):
        raise ValueError("A database session factory is required")

    def verify(expected_chat_id, expected_identity):
        if expected_chat_id != chat_id:
            return False

        with session_factory() as db:
            return verify_turn_binding(
                db,
                chat_id=expected_chat_id,
                user_id=user_id,
                base_identity=expected_identity,
                messages=messages,
                tools_spec=tools_spec,
            )

    async for line in guarded_persistent_turn(
        lines,
        chat_id=chat_id,
        capability=capability,
        slot_lock=slot_lock,
        coordinator=coordinator,
        expected_identity=base_identity,
        verify_identity=verify,
    ):
        yield line
