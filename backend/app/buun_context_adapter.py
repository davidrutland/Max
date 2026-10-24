"""Buun slot persistence HTTP adapter.

Transport only: no router discovery, chat ownership, database access,
or persistence capability activation.
"""

from dataclasses import dataclass

import httpx


class BuunContextError(RuntimeError):
    """A Buun slot operation failed or returned an unverified result."""


@dataclass(frozen=True)
class SlotTransferResult:
    n_tokens: int
    n_bytes: int
    duration_ms: float


class BuunContextAdapter:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def _post(
        self,
        child_url: str,
        slot_id: int,
        action: str,
        payload: dict,
    ) -> dict:
        if not isinstance(slot_id, int) or isinstance(slot_id, bool) or slot_id < 0:
            raise BuunContextError("Invalid slot ID")

        if not isinstance(child_url, str) or not child_url.startswith(
            ("http://", "https://")
        ):
            raise BuunContextError("Invalid child URL")

        url = f"{child_url.rstrip('/')}/slots/{slot_id}"

        try:
            response = await self.client.post(
                url,
                params={"action": action},
                json=payload,
                timeout=300.0,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BuunContextError(
                f"Buun slot {action} request failed: {exc}"
            ) from exc

        if not isinstance(result, dict):
            raise BuunContextError("Invalid Buun response")

        if result.get("id_slot") != slot_id:
            raise BuunContextError("Buun response slot ID mismatch")

        return result

    @staticmethod
    def _validate_filename(filename: str) -> None:
        if (
            not isinstance(filename, str)
            or not filename
            or filename in (".", "..")
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
        ):
            raise BuunContextError("Invalid snapshot filename")

    @staticmethod
    def _transfer_result(
        result: dict,
        action: str,
        filename: str,
    ) -> SlotTransferResult:
        is_save = action == "save"

        expected_outcome = "saved" if is_save else "installed_full"
        tokens_key = "n_saved" if is_save else "n_restored"
        bytes_key = "n_written" if is_save else "n_read"
        timing_key = "save_ms" if is_save else "restore_ms"

        resume = result.get("resume")
        timings = result.get("timings")

        if result.get("filename") != filename:
            raise BuunContextError("Snapshot filename mismatch")

        if not isinstance(resume, dict) or resume.get("outcome") != expected_outcome:
            raise BuunContextError(
                f"Buun {action} did not report {expected_outcome}"
            )

        if not isinstance(timings, dict):
            raise BuunContextError("Missing Buun timing information")

        tokens = result.get(tokens_key)
        n_bytes = result.get(bytes_key)
        duration = timings.get(timing_key)

        if (
            type(tokens) is not int
            or tokens <= 0
            or type(n_bytes) is not int
            or n_bytes <= 0
            or type(duration) not in (int, float)
            or not (0 <= duration < float("inf"))
        ):
            raise BuunContextError("Invalid Buun transfer measurements")

        if resume.get("n_tokens") != tokens:
            raise BuunContextError("Buun resume token count mismatch")

        return SlotTransferResult(
            n_tokens=tokens,
            n_bytes=n_bytes,
            duration_ms=float(duration),
        )

    async def save_slot(
        self,
        child_url: str,
        slot_id: int,
        filename: str,
    ) -> SlotTransferResult:
        self._validate_filename(filename)

        result = await self._post(
            child_url,
            slot_id,
            "save",
            {"filename": filename, "format": "resume"},
        )

        return self._transfer_result(result, "save", filename)

    async def restore_slot(
        self,
        child_url: str,
        slot_id: int,
        filename: str,
    ) -> SlotTransferResult:
        self._validate_filename(filename)

        result = await self._post(
            child_url,
            slot_id,
            "restore",
            {"filename": filename},
        )

        return self._transfer_result(result, "restore", filename)

    async def _router_post(
        self,
        router_url: str,
        alias: str,
        slot_id: int,
        action: str,
        payload: dict,
    ) -> dict:
        """Forward a slot operation through Buun's model router.

        autoload=false ensures persistence operations never load a model.
        """
        if not isinstance(alias, str) or not alias.strip():
            raise BuunContextError("Invalid model alias")
        if not isinstance(slot_id, int) or isinstance(slot_id, bool) or slot_id < 0:
            raise BuunContextError("Invalid slot ID")
        if not isinstance(router_url, str) or not router_url.startswith(("http://", "https://")):
            raise BuunContextError("Invalid router URL")

        url = f"{router_url.rstrip('/')}/slots/{slot_id}"
        try:
            response = await self.client.post(
                url,
                params={"action": action, "autoload": "false"},
                json={**payload, "model": alias},
                timeout=300.0,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BuunContextError(f"Buun router slot {action} failed: {exc}") from exc

        if not isinstance(result, dict) or result.get("id_slot") != slot_id:
            raise BuunContextError("Invalid Buun router slot response")
        return result

    async def save_via_router(
        self, router_url: str, alias: str, slot_id: int, filename: str
    ) -> SlotTransferResult:
        self._validate_filename(filename)
        result = await self._router_post(
            router_url, alias, slot_id, "save",
            {"filename": filename, "format": "resume"},
        )
        return self._transfer_result(result, "save", filename)

    async def restore_via_router(
        self, router_url: str, alias: str, slot_id: int, filename: str
    ) -> SlotTransferResult:
        self._validate_filename(filename)
        result = await self._router_post(
            router_url, alias, slot_id, "restore", {"filename": filename}
        )
        return self._transfer_result(result, "restore", filename)

    async def erase_via_router(
        self, router_url: str, alias: str, slot_id: int
    ) -> int:
        result = await self._router_post(router_url, alias, slot_id, "erase", {})
        n_erased = result.get("n_erased")
        if type(n_erased) is not int or n_erased < 0:
            raise BuunContextError("Invalid Buun router erase result")
        return n_erased

    async def erase_slot(
        self,
        child_url: str,
        slot_id: int,
    ) -> int:
        result = await self._post(child_url, slot_id, "erase", {})

        n_erased = result.get("n_erased")
        if type(n_erased) is not int or n_erased < 0:
            raise BuunContextError("Invalid Buun erase result")

        return n_erased
