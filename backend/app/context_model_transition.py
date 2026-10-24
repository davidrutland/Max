"""Switch a single Buun router slot between named models without modifying Buun.

Caller holds the shared inference lock. A model load may evict the previous
worker; no live slot may be reused after an uncertain transition.
"""
from app.buun_context_transport import BuunTransport, TransportMode


class ModelTransitionError(RuntimeError):
    pass


async def transition_model(coordinator, selected_model: str, load_model):
    transport = coordinator._transport.transport
    current = transport.target
    if not isinstance(selected_model, str) or not selected_model.strip():
        raise ModelTransitionError("Missing target model")
    if current.mode is not TransportMode.ROUTER:
        if current.alias != selected_model:
            raise ModelTransitionError("Cross-model transition requires a Buun router")
        return False
    if current.alias == selected_model:
        return False
    # This must succeed before any operation that could evict the old model.
    await coordinator.save_active()
    try:
        await load_model(selected_model)
    except Exception as exc:
        # The router might already have evicted the old worker.
        coordinator.orchestrator.uncertain = True
        raise ModelTransitionError("Model load failed; slot recovery required") from exc
    transport.target = BuunTransport(current.mode, current.url, alias=selected_model)
    # The new model has a different worker/slot, not the previous RAM state.
    coordinator.orchestrator.reset_after_external_recovery()
    return True
