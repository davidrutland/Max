"""Capture exact initial inference inputs for persistent identity checks.

No route wiring, inference or persistence activation.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.context_binding_repository import BindingIdentity
from app.context_turn_identity import identity_for_turn


@dataclass(frozen=True)
class PreparedTurnInputs:
    """Initial inference inputs, isolated from caller mutation."""

    messages: list[dict]
    tools_spec: Any

    @classmethod
    def capture(cls, messages: list[dict], tools_spec: Any):
        if not isinstance(messages, list):
            raise ValueError("Inference messages must be a list")
        return cls(
            messages=deepcopy(messages),
            tools_spec=deepcopy(tools_spec),
        )

    def expected_identity(self, base: BindingIdentity) -> BindingIdentity:
        return identity_for_turn(
            base,
            self.messages,
            self.tools_spec,
        )

    def inference_copy(self):
        """Return mutable copies for the agentic inference loop."""
        return deepcopy(self.messages), deepcopy(self.tools_spec)
