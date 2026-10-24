"""Initialize or verify a persistent conversation binding.

No transaction commits, model operations, coordinator registration or
persistence activation. Caller must hold the shared inference-slot lock.
"""

from app.context_binding_repository import (
    BindingIdentity,
    assert_identity,
    create_binding,
    replace_binding,
    get_binding,
)
from app.context_turn_identity import identity_for_turn


def ensure_turn_binding(
    db,
    *,
    chat_id: int,
    user_id: int,
    base_identity: BindingIdentity,
    messages: list[dict],
    tools_spec,
    allow_replace=False,
):
    """Stage a new binding or verify an existing immutable identity.

    The caller owns the transaction and must commit successfully before
    registering the conversation with the live coordinator.
    """
    expected = identity_for_turn(base_identity, messages, tools_spec)

    binding = get_binding(db, chat_id, user_id)

    if binding is None:
        return create_binding(db, chat_id, user_id, expected)

    if allow_replace:
        return replace_binding(db, chat_id, user_id, expected)
    assert_identity(binding, expected)
    return binding
