"""Verify actual turn inputs against an existing persistent binding.

This module does not create bindings or activate persistence.
"""

from app.context_binding_repository import (
    BindingIdentity,
    assert_identity,
    get_binding,
)
from app.context_turn_identity import identity_for_turn


class TurnBindingVerificationError(ValueError):
    """The turn cannot safely use the existing persistent binding."""


def verify_turn_binding(
    db,
    *,
    chat_id: int,
    user_id: int,
    base_identity: BindingIdentity,
    messages: list[dict],
    tools_spec,
) -> bool:
    """Verify a chat's saved identity against its actual inference inputs.

    Call while holding the shared slot lock, before switching slots.
    The database session belongs to the caller.
    """
    if not isinstance(base_identity, BindingIdentity):
        raise TurnBindingVerificationError(
            "Verified base identity required"
        )

    expected = identity_for_turn(
        base_identity,
        messages,
        tools_spec,
    )

    binding = get_binding(db, chat_id, user_id)

    if binding is None:
        raise TurnBindingVerificationError(
            "No persistent binding for chat"
        )

    assert_identity(binding, expected)

    return True
