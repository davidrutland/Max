"""Pure routing decisions for optional persistent inference contexts.

No database, network, inference, or snapshot operations belong here.
"""

from dataclasses import dataclass
from enum import Enum

from app.context_capabilities import ContextCapability


@dataclass(frozen=True)
class TargetIdentity:
    backend: str
    model_identity: str
    runtime_fingerprint: str
    # Informational routing fields: NEVER used to decide snapshot compatibility.
    endpoint: str = ""
    router_alias: str = ""

    def compatible_with(self, other: "TargetIdentity") -> bool:
        required = (self.backend, self.model_identity, self.runtime_fingerprint,
                    other.backend, other.model_identity, other.runtime_fingerprint)
        return all(isinstance(v, str) and bool(v.strip()) for v in required) and (
            self.backend, self.model_identity, self.runtime_fingerprint
        ) == (
            other.backend, other.model_identity, other.runtime_fingerprint
        )


@dataclass(frozen=True)
class ChatBinding:
    target: TargetIdentity
    instructions_fingerprint: str


class ChatEngine(str, Enum):
    LEGACY = "legacy"
    PERSISTENT = "persistent"
    FORK_REQUIRED = "fork_required"


@dataclass(frozen=True)
class DispatchDecision:
    engine: ChatEngine
    reason: str


def select_chat_engine(
    capability: ContextCapability,
    chat_binding: ChatBinding | None,
    requested_target: TargetIdentity,
    requested_instructions_fingerprint: str | None = None,
) -> DispatchDecision:
    """Choose an engine without changing chat ownership or inference state.

    Callers must separately enforce FORK_REQUIRED before any message writes.
    Missing identity or instruction fingerprints cannot prove compatibility.
    """
    if chat_binding is None:
        return DispatchDecision(ChatEngine.LEGACY, "Unbound legacy conversation")

    if not requested_target.compatible_with(chat_binding.target):
        return DispatchDecision(ChatEngine.FORK_REQUIRED, "Backend, model or runtime identity differs or is unverified")

    if (not isinstance(requested_instructions_fingerprint, str)
            or not requested_instructions_fingerprint.strip()
            or requested_instructions_fingerprint != chat_binding.instructions_fingerprint):
        return DispatchDecision(ChatEngine.FORK_REQUIRED, "System instructions differ or cannot be verified")

    if not capability.supported:
        return DispatchDecision(ChatEngine.LEGACY, "Persistence unavailable; original target preserved")

    if capability.backend != requested_target.backend:
        return DispatchDecision(ChatEngine.LEGACY, "Capability is for a different backend")

    # When the adapter supplies identity claims, they must match the verified target.
    if (capability.model_identity is not None
            and capability.model_identity != requested_target.model_identity):
        return DispatchDecision(ChatEngine.LEGACY, "Capability model identity does not match")
    if (capability.runtime_fingerprint is not None
            and capability.runtime_fingerprint != requested_target.runtime_fingerprint):
        return DispatchDecision(ChatEngine.LEGACY, "Capability runtime fingerprint does not match")

    return DispatchDecision(ChatEngine.PERSISTENT, "Verified persistence capability")
