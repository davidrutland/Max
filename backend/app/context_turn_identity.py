"""Construct expected binding identity from actual inference inputs.

Pure, offline helper. Does not create bindings, switch slots or
activate persistence.
"""

from dataclasses import replace

from app.context_binding_repository import BindingIdentity
from app.context_tool_identity import tool_fingerprint


class TurnIdentityError(ValueError):
    pass


def identity_for_turn(
    base: BindingIdentity,
    messages: list[dict],
    tools_spec,
) -> BindingIdentity:
    """Replace turn-dependent identity fields using actual model inputs.

    The caller must supply verified backend/model/runtime identity.
    A missing or ambiguous system message fails closed.
    """
    if not isinstance(base, BindingIdentity):
        raise TurnIdentityError("Verified base BindingIdentity required")

    if not isinstance(messages, list) or not messages:
        raise TurnIdentityError("Inference messages required")

    if not isinstance(messages[0], dict) or messages[0].get("role") != "system":
        raise TurnIdentityError(
            "Persistent turn requires an effective system message"
        )

    prompt = messages[0].get("content")
    if not isinstance(prompt, str) or not prompt:
        raise TurnIdentityError(
            "Effective system prompt must be nonempty text"
        )

    if any(
        not isinstance(m, dict) or m.get("role") == "system"
        for m in messages[1:]
    ):
        raise TurnIdentityError("Unexpected additional system message")

    return replace(
        base,
        effective_system_prompt=prompt,
        tool_fingerprint=tool_fingerprint(tools_spec),
    )
