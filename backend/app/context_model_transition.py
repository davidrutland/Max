"""Switch a single Buun router slot between named models without modifying Buun.

Caller holds the shared inference lock. A model load may evict the previous
worker; no live slot may be reused after an uncertain transition.
"""
from app.buun_context_transport import BuunTransport, TransportMode


class ModelTransitionError(RuntimeError):
    pass


async def transition_model(coordinator, selected_model: str, load_model, get_status=None):
    """Save only through the worker that actually owns the outgoing slot.

    A router may evict its worker independently of our in-process state.
    Never send a stale checkpoint save to a different worker.
    """
    transport = coordinator._transport.transport
    current = transport.target
    if not isinstance(selected_model, str) or not selected_model.strip():
        raise ModelTransitionError("Missing target model")
    if current.mode is not TransportMode.ROUTER:
        if current.alias != selected_model:
            raise ModelTransitionError("Cross-model transition requires a Buun router")
        return False

    loaded = True
    if get_status is not None:
        try:
            loaded = await get_status(current.alias) == "loaded"
        except Exception as exc:
            raise ModelTransitionError("Cannot verify outgoing router worker") from exc

    if not loaded:
        # The worker vanished. A dirty RAM context cannot be recovered from a
        # different worker; never replace its last committed checkpoint.
        if coordinator.orchestrator.dirty:
            coordinator.orchestrator.uncertain = True
            raise ModelTransitionError("Outgoing worker lost unsaved context; recovery required")
    elif current.alias != selected_model:
        # Must complete before loading a worker that could evict this one.
        await coordinator.save_active()

    if current.alias == selected_model and loaded:
        return False
    try:
        await load_model(selected_model)
    except Exception as exc:
        coordinator.orchestrator.uncertain = True
        raise ModelTransitionError("Model load failed; slot recovery required") from exc
    transport.target = BuunTransport(current.mode, current.url, alias=selected_model)
    coordinator.orchestrator.reset_after_external_recovery()
    return True
