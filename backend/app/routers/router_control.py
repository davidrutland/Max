"""Buun router model status and control."""

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.context_slot_owner import SlotOwnerError, slot_owners

from app import auth, models, config
from app.buun_model_loader import BuunModelLoader, ModelLoadError

router = APIRouter(prefix="/api/router", tags=["router"])


@router.get("/models")
async def router_models(
    _user: models.User = Depends(auth.get_current_user),
):
    url = os.environ.get("BUUN_CONTEXT_URL", "").strip()
    if not url:
        raise HTTPException(503, "Buun router not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{url.rstrip('/')}/v1/models")
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, "Cannot reach Buun router") from exc

    result = []
    for entry in data.get("data", []):
        status = entry.get("status", {})
        result.append({
            "model": entry["id"],
            "status": status.get("value", "unknown"),
        })
    if config.CONTEXT_PERSISTENCE_MODE != "auto":
        return {"server_id": None, "models": result}

    try:
        owner = slot_owners.require()
    except SlotOwnerError:
        raise HTTPException(503, "No verified inference-slot owner")

    return {"server_id": owner.server_id, "models": result}


class ModelSelection(BaseModel):
    model: str


@router.post("/select")
async def select_model(
    payload: ModelSelection,
    _user: models.User = Depends(auth.get_current_user),
):
    url = os.environ.get("BUUN_CONTEXT_URL", "").strip()
    if not url:
        raise HTTPException(503, "Buun router not configured")

    model = payload.model.strip()
    if not model:
        raise HTTPException(422, "Model name required")

    if config.CONTEXT_PERSISTENCE_MODE != "auto":
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                loader = BuunModelLoader(url, client)
                return {"model": model, "status": await loader.load(model)}
            except ModelLoadError as exc:
                raise HTTPException(502, str(exc)) from exc

    try:
        owner = slot_owners.require()
    except SlotOwnerError as exc:
        raise HTTPException(503, "No verified inference-slot owner") from exc

    async with owner.lock:
        async with httpx.AsyncClient(timeout=30.0) as client:
            loader = BuunModelLoader(url, client)

            try:
                status = await loader.status(model)

                if status == "loaded":
                    return {"model": model, "status": status}

                if status == "loading":
                    return {"model": model, "status": status}

                if status != "unloaded":
                    raise HTTPException(
                        409, f"Model cannot be selected: {status}"
                    )

                # After a Buun restart the backend may still believe its old
                # worker owns a dirty slot. With no loaded worker that RAM slot
                # no longer exists: never attempt to save it over the durable
                # checkpoint. A genuine model switch must still save first.
                inventory = await client.get(f"{url.rstrip('/')}/v1/models")
                inventory.raise_for_status()
                entries = inventory.json()["data"]
                workers_live = any(
                    entry.get("status", {}).get("value") in ("loaded", "loading")
                    for entry in entries
                )
                if workers_live:
                    await owner.coordinator.save_active()
                    owner.coordinator.orchestrator.release_active()
                else:
                    owner.coordinator.orchestrator.reset_after_external_recovery()

                status = await loader.load(model)

                return {"model": model, "status": status}

            except ModelLoadError as exc:
                raise HTTPException(502, str(exc)) from exc
