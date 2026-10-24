"""Explicit Buun persistence eligibility; no probes or side effects."""

import os


class BuunSelectionError(ValueError):
    pass


def parse_buun_server_id(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise BuunSelectionError("CONTEXT_BUUN_SERVER_ID must be a positive integer")
    number = int(value)
    if number <= 0:
        raise BuunSelectionError("CONTEXT_BUUN_SERVER_ID must be a positive integer")
    return number


def configured_buun_server_id() -> int | None:
    return parse_buun_server_id(os.environ.get("CONTEXT_BUUN_SERVER_ID"))


def require_buun_target(
    target: dict,
    *,
    configured_server_id: int | None,
) -> dict:
    if configured_server_id is None:
        raise BuunSelectionError("Buun persistence server is not configured")

    if not isinstance(target, dict):
        raise BuunSelectionError("Invalid server target")

    if type(target.get("id")) is not int or target["id"] != configured_server_id:
        raise BuunSelectionError("Selected server is not the configured Buun server")

    if target.get("type") != "openai":
        raise BuunSelectionError("Configured Buun server must use OpenAI-compatible transport")

    url = target.get("base_url")
    if not isinstance(url, str) or not url.strip():
        raise BuunSelectionError("Configured Buun server URL is missing")

    return target
