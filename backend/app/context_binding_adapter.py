"""Construct a name-based persistent-context binding.

The configured server and model name are the operational identity.
Legacy metadata columns remain populated until a future schema migration.
No network access, model inspection, or filesystem hashing.
"""

from app.context_binding_repository import BindingIdentity


class BindingAdapterError(ValueError):
    pass


def binding_base_for_target(
    *,
    selected_model: str,
    backend_identity: str,
) -> BindingIdentity:
    if not isinstance(selected_model, str) or not selected_model.strip():
        raise BindingAdapterError("Selected model is required")

    if not isinstance(backend_identity, str) or not backend_identity.strip():
        raise BindingAdapterError("Backend identity is required")

    return BindingIdentity(
        backend_identity=backend_identity,
        router_alias=selected_model,
        model_path="name-based",
        model_fingerprint="0" * 64,
        mmproj_path=None,
        mmproj_fingerprint=None,
        model_identity="name-based",
        backend_build="name-based",
        runtime_fingerprint="name-based",
        effective_system_prompt="",
        tool_fingerprint="",
    )
