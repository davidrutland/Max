"""Thin client for the bundled SearXNG JSON API.

`SEARXNG_URL/search?format=json` → returns [{title, url, content}]. On failure (SearXNG
down, timeout, malformed response) it does not raise, so the caller can carry on — it
returns an empty list instead.
"""
import os

import httpx

from app.config import SEARXNG_URL, SEARCH_TIMEOUT

SEARCH_SERVICE_URL = os.environ.get(
    "SEARCH_SERVICE_URL",
    "http://host.docker.internal:8787",
).rstrip("/")


async def search(query: str, n: int = 5) -> list[dict]:
    url = SEARXNG_URL.rstrip("/") + "/search"
    params = {"q": query, "format": "json"}
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    results = []
    for r in (data.get("results") or [])[:n]:
        results.append(
            {
                "title": (r.get("title") or "").strip(),
                "url": (r.get("url") or "").strip(),
                "content": (r.get("content") or "").strip(),
            }
        )
    return results


MAX_RESULT_CHARS = 800  # per-result content cap: limits injection surface and context bloat


async def fetch(url: str) -> dict:
    """Fetch a URL through the local search/retrieval service."""
    target = SEARCH_SERVICE_URL + "/fetch"

    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            resp = await client.get(target, params={"url": url})
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return {
            "ok": False,
            "url": url,
            "error": "Web page fetch failed.",
        }

    if not isinstance(data, dict):
        return {
            "ok": False,
            "url": url,
            "error": "Web page fetch returned an invalid response.",
        }

    if not data.get("ok"):
        return {
            "ok": False,
            "url": url,
            "error": data.get("error") or "Web page fetch failed.",
        }

    return {
        "ok": True,
        "url": (data.get("url") or url).strip(),
        "title": (data.get("title") or "").strip(),
        "content": data.get("content") or "",
    }


def format_fetch(result: dict) -> str:
    """Render a fetched page as model-readable text."""
    if not result.get("ok"):
        return f"ERROR: {result.get('error') or 'Web page fetch failed.'}"

    lines = [
        f"Web page fetched: {result.get('url', '')}",
    ]

    title = (result.get("title") or "").strip()
    if title:
        lines.extend(["", f"Title: {title}"])

    content = result.get("content") or ""
    if content:
        lines.extend(["", content])

    return "\n".join(lines).strip()


def format_results(query: str, results: list[dict]) -> str:
    """Renders search results into a plain-text context block for the model."""
    lines = [f"Web search results (query: {query}):", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}" if r["title"] else f"{i}.")
        if r["url"]:
            lines.append(r["url"])
        if r["content"]:
            content = r["content"]
            if len(content) > MAX_RESULT_CHARS:
                content = content[:MAX_RESULT_CHARS] + " […]"
            lines.append(content)
        lines.append("")
    return "\n".join(lines).strip()
