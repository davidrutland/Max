"""Read-only compatibility decision for a proposed persistent chat turn."""
from dataclasses import dataclass

from app.context_binding_repository import BindingIdentity
from app.context_turn_identity import identity_for_turn


@dataclass(frozen=True)
class CompatibilityDecision:
    compatible: bool
    reasons: tuple[str, ...]
    initialized: bool

    def as_dict(self) -> dict:
        return {
            "compatible": self.compatible,
            "requires_confirmation": not self.compatible,
            "reasons": list(self.reasons),
            "initialized": self.initialized,
        }


def check_compatibility(binding, *, base_identity: BindingIdentity,
                        messages: list[dict], tools_spec) -> CompatibilityDecision:
    """Compare actual proposed inference inputs to saved identity; never mutate.

    A missing binding is a new conversation, not a mismatch. Backend identity
    is operational metadata; model identity is the router alias alone.
    """
    expected = identity_for_turn(base_identity, messages, tools_spec)
    if binding is None:
        return CompatibilityDecision(True, (), False)

    reasons = []
    if binding.router_alias != expected.router_alias:
        reasons.append("model")
    if binding.effective_system_prompt != expected.effective_system_prompt:
        reasons.append("system_prompt")
    if binding.tool_fingerprint != expected.tool_fingerprint:
        reasons.append("tools")
    return CompatibilityDecision(not reasons, tuple(reasons), True)
