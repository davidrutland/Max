"""Read-only discovery of loaded Buun router child processes.

Child endpoints are ephemeral routing information, not model identity.
No model loading, unloading, or context operations occur here.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


class BuunRouterError(RuntimeError):
    """The router could not provide a verified loaded child endpoint."""


@dataclass(frozen=True)
class LoadedModel:
    alias: str
    child_url: str
    port: int


def _extract_port(args: list) -> int:
    if not isinstance(args, list):
        raise BuunRouterError("Invalid model process arguments")

    ports = [
        args[i + 1]
        for i, value in enumerate(args[:-1])
        if value == "--port"
    ]

    if len(ports) != 1:
        raise BuunRouterError("Missing or ambiguous child port")

    value = ports[0]

    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise BuunRouterError("Invalid child port")

    port = int(value)

    if not 1 <= port <= 65535:
        raise BuunRouterError("Child port outside valid range")

    return port


async def resolve_loaded_model(
    client: httpx.AsyncClient,
    router_url: str,
    alias: str,
) -> LoadedModel:
    """Resolve an already-loaded model without activating it."""

    if not isinstance(alias, str) or not alias.strip():
        raise BuunRouterError("Invalid model alias")

    if not isinstance(router_url, str):
        raise BuunRouterError("Invalid router URL")

    try:
        parsed = urlsplit(router_url)

        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise BuunRouterError("Invalid router URL")

        # Also validate an explicitly supplied router port.
        _ = parsed.port

    except ValueError as exc:
        raise BuunRouterError("Invalid router URL") from exc

    try:
        response = await client.get(
            router_url.rstrip("/") + "/models",
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()

    except (httpx.HTTPError, ValueError) as exc:
        raise BuunRouterError(
            f"Buun router discovery failed: {exc}"
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise BuunRouterError("Malformed router models response")

    matches = [
        item for item in payload["data"]
        if isinstance(item, dict) and item.get("id") == alias
    ]

    if len(matches) != 1:
        raise BuunRouterError("Model alias missing or ambiguous")

    status = matches[0].get("status")

    if not isinstance(status, dict) or status.get("value") != "loaded":
        raise BuunRouterError("Model is not confirmed loaded")

    port = _extract_port(status.get("args"))

    # The router and its children must be reachable on the same host.
    # Use the router's hostname, not the child's advertised --host.
    host = parsed.hostname

    if ":" in host:
        host = f"[{host}]"

    child_url = f"{parsed.scheme}://{host}:{port}"

    return LoadedModel(
        alias=alias,
        child_url=child_url,
        port=port,
    )
