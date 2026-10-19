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

import httpx

from slackx.rpc.protocol import RpcError


class RpcTransportError(RuntimeError):
    """The server could not be reached, or its response was not JSON-RPC."""


class RpcClient:
    """A minimal JSON-RPC 2.0 client over HTTP."""

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url
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
        try:
            response = await self._client.post(self.url, json=request)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RpcTransportError(f"could not reach {self.url}: {exc}") from exc

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
        result = await self.call("system.methods")
        return list(result.get("methods", []))

    async def aclose(self) -> None:
        """Close the underlying HTTP client when this instance owns it."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> RpcClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
