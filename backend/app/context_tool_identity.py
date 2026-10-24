"""Deterministic identity of the exact tools offered to a persistent turn.

No route integration or snapshot operations. Tool changes require a fork.
"""
import hashlib
import json
from collections.abc import Mapping


class ToolIdentityError(ValueError):
    pass


def tool_fingerprint(tools_spec) -> str:
    """Fingerprint the exact tool payload, including schemas and ordering.

    None means no tools; [] is treated as the same no-tools state.
    Reject non-JSON payloads rather than silently hashing a string repr.
    """
    if tools_spec is None:
        tools_spec = []
    if not isinstance(tools_spec, (list, tuple)):
        raise ToolIdentityError("Tool specifications must be a sequence")
    if not all(isinstance(item, Mapping) for item in tools_spec):
        raise ToolIdentityError("Each tool specification must be an object")
    try:
        payload = json.dumps(
            list(tools_spec), sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ToolIdentityError("Tool specifications must be finite JSON values") from exc
    return hashlib.sha256(payload).hexdigest()


def require_same_tools(saved_fingerprint: str, current_fingerprint: str) -> None:
    """Fail closed: an altered tool contract needs a separate conversation."""
    if (not isinstance(saved_fingerprint, str)
            or not isinstance(current_fingerprint, str)
            or len(saved_fingerprint) != 64
            or len(current_fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in saved_fingerprint + current_fingerprint)):
        raise ToolIdentityError("Missing or invalid tool fingerprint; fork required")
    if saved_fingerprint != current_fingerprint:
        raise ToolIdentityError("Tool configuration changed; fork required")
