"""Async JSON-RPC client for a running slackx server.

Use it from Python when a long-lived server should do the work instead of
spawning the CLI::

    from slackx.rpc.client import RpcClient

    async with RpcClient("http://127.0.0.1:8280/rpc") as client:
        status = await client.call("cache.status")
        users = await client.call("users.list", {"limit": 20})

The client raises :class:`RpcError` for JSON-RPC error responses and
:class:`RpcTransportError` when the server cannot be reached or the HTTP/JSON
exchange fails. It imports httpx, so CLI help paths must import it lazily.
"""

from __future__ import annotations

import itertools
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from slackx.rpc.protocol import RpcError


def endpoint_url(url: str) -> str:
    """Normalize a server address to the ``/rpc`` path.

    A bare host or a host with a port is accepted, matching the server's
    printed URL, so ``--url http://127.0.0.1:8280`` reaches ``/rpc``.
    """
    raw = url.strip()
    if "://" not in raw:
        raw = f"http://{raw}"
    parts = urlsplit(raw)
    path = parts.path or "/rpc"
    if path == "/":
        path = "/rpc"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


class RpcTransportError(RuntimeError):
    """The server could not be reached, or its response was not JSON-RPC."""


class RpcClient:
    """A minimal JSON-RPC 2.0 client over HTTP."""

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = endpoint_url(url)
        self.token = token
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._ids = itertools.count(1)

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Call ``method`` and return its result, raising on JSON-RPC errors."""
        request = {
            "jsonrpc": "2.0",
            "id": next(self._ids),
            "method": method,
            "params": params or {},
        }
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        try:
            response = await self._client.post(self.url, json=request, headers=headers)
        except httpx.HTTPError as exc:
            raise RpcTransportError(f"could not reach {self.url}: {exc}") from exc
        if response.status_code == 401:
            raise RpcTransportError(f"server at {self.url} rejected the token (HTTP 401)")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RpcTransportError(
                f"server at {self.url} returned HTTP {response.status_code}: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RpcTransportError(f"server at {self.url} returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise RpcTransportError(f"server at {self.url} returned an unexpected payload")
        error = payload.get("error")
        if isinstance(error, dict):
            raise RpcError(
                int(error.get("code", -32603)),
                str(error.get("message", "JSON-RPC error")),
                error.get("data"),
            )
        if "result" not in payload:
            raise RpcTransportError(f"server at {self.url} returned no result")
        return payload["result"]

    async def methods(self) -> list[dict[str, Any]]:
        """Return the server's method catalog."""
        result = await self.call("rpc.discover")
        return list(result.get("methods", []))

    async def exec(self, args: list[str], stdin: str = "") -> dict[str, Any]:
        """Run a CLI command on the server and return its output and exit code."""
        return await self.call("cli.run", {"args": args, "stdin": stdin})

    async def aclose(self) -> None:
        """Close the underlying HTTP client when this instance owns it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> RpcClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
