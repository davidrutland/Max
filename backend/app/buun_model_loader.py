"""Explicit model loading through a llama.cpp/Buun router."""

import httpx


class ModelLoadError(RuntimeError):
    pass


class BuunModelLoader:
    def __init__(self, router_url: str, client: httpx.AsyncClient | None = None):
        self.router_url = router_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=30.0)

    async def status(self, model: str) -> str:
        try:
            response = await self.client.get(
                f"{self.router_url}/v1/models"
            )
            response.raise_for_status()
            models = response.json()["data"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ModelLoadError("Cannot read router model status") from exc

        for entry in models:
            if entry.get("id") == model:
                status = entry.get("status", {}).get("value")
                if not isinstance(status, str):
                    raise ModelLoadError("Invalid router model status")
                return status

        raise ModelLoadError(f"Model not found: {model}")

    async def load(self, model: str) -> str:
        current = await self.status(model)

        if current in ("loaded", "loading"):
            return current

        if current != "unloaded":
            raise ModelLoadError(
                f"Cannot load {model}: router status is {current}"
            )

        try:
            response = await self.client.post(
                f"{self.router_url}/models/load",
                json={"model": model},
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ModelLoadError(f"Failed to load {model}") from exc

        if result.get("success") is not True:
            raise ModelLoadError(f"Router rejected loading {model}")

        return await self.status(model)
