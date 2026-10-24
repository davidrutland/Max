"""Fail-closed pre-switch identity verification for an opt-in persistent turn.

No route wiring, DB access or capability inference occurs here. The caller must
supply an independently constructed expected identity and a verifier which
checks the persisted binding against that identity.
"""
import asyncio
import inspect
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.context_turn_preflight import PersistentTurnPlan, prepare_persistent_turn


class ContextIdentityError(RuntimeError):
    pass


async def guarded_persistent_turn(
    lines: AsyncIterator[str], *, chat_id: int, capability: Any,
    slot_lock: asyncio.Lock, coordinator: Any, expected_identity: Any,
    verify_identity: Callable[[int, Any], Any],
) -> AsyncIterator[str]:
    """Verify under the slot lock, then switch and run the entire turn.

    The verifier must compare *all* persisted compatibility fields, including
    the exact effective system prompt. It must raise on absent/mismatched state.
    """
    plan: PersistentTurnPlan = prepare_persistent_turn(capability, slot_lock)
    if type(chat_id) is not int or chat_id < 1:
        raise ContextIdentityError("A positive chat ID is required")
    if expected_identity is None or not callable(verify_identity):
        raise ContextIdentityError("Expected identity and verifier are required")
    if not callable(getattr(coordinator, "switch", None)) or not callable(getattr(coordinator, "mark_dirty", None)):
        raise ContextIdentityError("A context coordinator is required")

    async with plan.slot_lock:
        try:
            result = verify_identity(chat_id, expected_identity)
            if inspect.isawaitable(result):
                result = await result
            # Only an explicit True is proof. None/false/objects fail closed.
            if result is not True:
                raise ContextIdentityError("Persisted context identity was not verified")
            await coordinator.switch(chat_id)
            coordinator.mark_dirty(chat_id)
            async for line in lines:
                yield line
        finally:
            await lines.aclose()
