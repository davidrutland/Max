"""Fail-closed preflight for future persistent turns.

This module does not activate persistence or touch chat routes. Callers must
supply an independently verified capability and a shared slot lock.
"""
import asyncio
from dataclasses import dataclass

from app.context_capabilities import ContextCapability
from app.context_turn_boundary import wrap


class ContextPreflightError(RuntimeError):
    pass


@dataclass(frozen=True)
class PersistentTurnPlan:
    capability: ContextCapability
    slot_lock: asyncio.Lock


def prepare_persistent_turn(capability: ContextCapability,
                            slot_lock: asyncio.Lock | None) -> PersistentTurnPlan:
    """Validate prerequisites; never infer support from a backend name."""
    if not isinstance(capability, ContextCapability) or capability.supported is not True:
        raise ContextPreflightError("Persistence backend is not verified")
    if not isinstance(slot_lock, asyncio.Lock):
        raise ContextPreflightError("A shared inference-slot lock is required")
    return PersistentTurnPlan(capability, slot_lock)


def wrap_planned_turn(lines, plan: PersistentTurnPlan):
    """Apply the existing turn boundary only after preflight succeeds."""
    if not isinstance(plan, PersistentTurnPlan):
        raise ContextPreflightError("Missing persistent turn plan")
    return wrap(lines, enabled=True, slot_lock=plan.slot_lock)
