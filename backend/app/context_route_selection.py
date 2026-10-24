"""Fail-closed selection of the optional persistent inference route.

Selection does not install an owner, switch models, restore snapshots,
or activate persistence. The caller must still wire the selected route.
"""

from dataclasses import dataclass

from app.context_capabilities import ContextCapability
from app.context_slot_owner import SlotOwnerRegistry, SlotOwner


class ContextRouteSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContextRouteSelection:
    persistent: bool
    owner: SlotOwner | None = None


def select_context_route(
    *,
    mode: str,
    capability: ContextCapability | None,
    owners: SlotOwnerRegistry,
) -> ContextRouteSelection:
    if mode == "disabled":
        return ContextRouteSelection(persistent=False)

    if mode != "auto":
        raise ContextRouteSelectionError("Invalid context persistence mode")

    if not isinstance(capability, ContextCapability):
        raise ContextRouteSelectionError("No verified context capability")

    if capability.supported is not True:
        raise ContextRouteSelectionError("Context persistence is not supported")


    if not isinstance(owners, SlotOwnerRegistry):
        raise ContextRouteSelectionError("Invalid inference-slot registry")

    try:
        owner = owners.require()
    except Exception as exc:
        raise ContextRouteSelectionError(
            "No verified inference-slot owner"
        ) from exc

    return ContextRouteSelection(persistent=True, owner=owner)
