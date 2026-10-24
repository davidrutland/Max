"""Persistence capability contract; no probes or save/restore operations yet."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextCapability:
    supported: bool
    backend: str
    reason: str
    model_identity: str | None = None
    runtime_fingerprint: str | None = None


def detect_context_capability(backend: str, mode: str = "disabled") -> ContextCapability:
    """Fail closed until a backend adapter has been verified."""
    if mode not in ("auto", "disabled"):
        raise ValueError("mode must be 'auto' or 'disabled'")
    reason = (
        "Persistence disabled by configuration"
        if mode == "disabled"
        else "No verified persistence adapter is installed"
    )
    return ContextCapability(supported=False, backend=backend, reason=reason)
