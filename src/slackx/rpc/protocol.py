"""JSON-RPC 2.0 protocol types, error codes, and request validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VERSION = "2.0"

# JSON-RPC 2.0 predefined error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Implementation-defined server error (application failures such as a missing
# cache row, no Slack credentials, or a Slack API error).
SERVER_ERROR = -32000

DEFAULT_RPC_PORT = 8280
DEFAULT_RPC_URL = f"http://127.0.0.1:{DEFAULT_RPC_PORT}/rpc"


class RpcError(Exception):
    """An error that maps to a JSON-RPC error object.

    ``code`` follows the JSON-RPC 2.0 reserved ranges. ``data`` is optional and
    carried through to the response for callers that want more detail.
    """

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def payload(self) -> dict[str, Any]:
        """Return the JSON-RPC ``error`` object for this exception."""
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error


@dataclass(frozen=True)
class RpcRequest:
    """A validated JSON-RPC request."""

    method: str
    params: dict[str, Any]
    id: str | int | None
    is_notification: bool


def parse_request(payload: Any) -> RpcRequest:
    """Validate a decoded JSON-RPC request and return it.

    Raises :class:`RpcError` with ``INVALID_REQUEST`` when the payload is not a
    well-formed JSON-RPC 2.0 request object. Params must be a JSON object (or
    absent); by-position params are not supported.
    """
    if not isinstance(payload, dict):
        raise RpcError(INVALID_REQUEST, "Invalid Request", "A request must be a JSON object")
    if payload.get("jsonrpc") != VERSION:
        raise RpcError(INVALID_REQUEST, "Invalid Request", "jsonrpc must be '2.0'")
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        raise RpcError(INVALID_REQUEST, "Invalid Request", "method must be a non-empty string")

    params = payload.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise RpcError(INVALID_REQUEST, "Invalid Request", "params must be a JSON object")

    has_id = "id" in payload
    request_id = payload.get("id")
    if isinstance(request_id, bool) or not (
        request_id is None or isinstance(request_id, (str, int))
    ):
        raise RpcError(INVALID_REQUEST, "Invalid Request", "id must be a string, number, or null")

    return RpcRequest(
        method=method,
        params=params,
        id=request_id,
        is_notification=not has_id,
    )


def success_response(request_id: str | int | None, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC success response."""
    return {"jsonrpc": VERSION, "id": request_id, "result": result}


def error_response(
    request_id: str | int | None,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC error response."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": VERSION, "id": request_id, "error": error}
