"""Deferred preparation under exclusive persistent slot ownership.

Not connected to the live chat route. Does not activate persistence.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.context_binding_repository import BindingIdentity
from app.context_prepared_inputs import PreparedTurnInputs
from app.context_turn_preflight import ContextPreflightError, prepare_persistent_turn
from app.context_turn_verification import verify_turn_binding


async def deferred_persistent_turn(
    *,
    chat_id: int,
    user_id: int,
    capability: Any,
    slot_lock: asyncio.Lock,
    coordinator: Any,
    session_factory: Callable,
    base_identity: BindingIdentity,
    prepare: Callable,
    infer: Callable,
    initialize_registration: Callable | None = None,
    require_active: bool = False,
    check_ready: Callable | None = None,
    snapshot_turn_interval: int = 0,
    allow_configuration_change: bool = False,
) -> AsyncIterator[str]:
    """Prepare, verify and infer under one shared lock.

    prepare() returns (messages, tools_spec), possibly asynchronously.
    infer(messages, tools_spec) returns an async iterator.

    Neither preparation nor inference runs before acquiring the lock.
    The database session closes before switching or inference.
    """
    plan = prepare_persistent_turn(capability, slot_lock)

    if type(chat_id) is not int or chat_id < 1:
        raise ValueError("A positive chat ID is required")
    if type(user_id) is not int or user_id < 1:
        raise ValueError("A positive user ID is required")
    if not isinstance(base_identity, BindingIdentity):
        raise ValueError("A verified base identity is required")
    if not all(callable(x) for x in (session_factory, prepare, infer)):
        raise ValueError("Session factory, prepare and infer are required")
    if not callable(getattr(coordinator, "switch", None)):
        raise ValueError("A context coordinator is required")
    if not callable(getattr(coordinator, "mark_dirty", None)):
        raise ValueError("A context coordinator is required")

    async with plan.slot_lock:
        if require_active and coordinator.active_chat_id != chat_id:
            raise ContextPreflightError(
                "Conversation is not active; activate it before sending a message"
            )
        if check_ready is not None:
            result = check_ready()
            if asyncio.iscoroutine(result):
                await result

        lines = None
        try:
            result = prepare()
            if asyncio.iscoroutine(result):
                result = await result

            messages, tools_spec = result
            prepared = PreparedTurnInputs.capture(messages, tools_spec)

            if initialize_registration is not None:
                replaced = initialize_registration(
                    session_factory=session_factory,
                    coordinator=coordinator,
                    slot_lock=plan.slot_lock,
                    chat_id=chat_id,
                    user_id=user_id,
                    base_identity=base_identity,
                    messages=prepared.messages,
                    tools_spec=prepared.tools_spec,
                    allow_replace=allow_configuration_change,
                )
                if replaced:
                    await coordinator.discard_replaced_context(chat_id)
            else:
                with session_factory() as db:
                    verified = verify_turn_binding(
                        db,
                        chat_id=chat_id,
                        user_id=user_id,
                        base_identity=base_identity,
                        messages=prepared.messages,
                        tools_spec=prepared.tools_spec,
                    )

                if verified is not True:
                    raise ValueError("Persistent binding was not verified")

            await coordinator.switch(chat_id)
            coordinator.mark_dirty(chat_id)

            inference_messages, inference_tools = prepared.inference_copy()
            lines = infer(inference_messages, inference_tools)

            async for line in lines:
                yield line
            # Close the inference stream before checkpointing: stream cleanup may
            # persist the final assistant message or finish backend operations.
            await lines.aclose()
            lines = None
            # Only a fully completed turn counts; cancelled/failed turns stay dirty.
            if snapshot_turn_interval > 0:
                await coordinator.completed_turn(chat_id, snapshot_turn_interval)
        finally:
            if lines is not None:
                await lines.aclose()
