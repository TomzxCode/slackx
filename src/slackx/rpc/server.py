"""JSON-RPC 2.0 HTTP endpoint for the slackx server.

The endpoint lives at ``POST /rpc`` on the app built by
``slackx.server.app.create_app``. It accepts a single request object or a
batch (JSON array), supports notifications (a request without ``id``), and
always answers request-level failures with a JSON-RPC error object and HTTP
200, as the specification requires.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from slackx.rpc.methods import RpcContext, dispatch
from slackx.rpc.protocol import (
    INVALID_REQUEST,
    PARSE_ERROR,
    RpcError,
    error_response,
    parse_request,
    success_response,
)

RPC_PATH = "/rpc"


async def _handle_one(ctx: RpcContext, payload: Any) -> dict[str, Any] | None:
    """Handle one request object, returning None for a notification."""
    try:
        request = parse_request(payload)
    except RpcError as exc:
        return error_response(None, exc.code, exc.message, exc.data)

    try:
        result = await dispatch(ctx, request.method, request.params)
    except RpcError as exc:
        if request.is_notification:
            return None
        return error_response(request.id, exc.code, exc.message, exc.data)

    if request.is_notification:
        return None
    return success_response(request.id, result)


def add_rpc_routes(
    fastapp: FastAPI,
    db_path: Path,
    api_base_url: str | None = None,
    log_level: str = "info",
) -> None:
    """Register the JSON-RPC endpoint on ``fastapp``."""
    ctx = RpcContext(db_path=db_path, api_base_url=api_base_url, log_level=log_level)

    @fastapp.post(RPC_PATH, include_in_schema=False)
    async def json_rpc(request: Request) -> Response:
        try:
            payload = json.loads(await request.body())
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(error_response(None, PARSE_ERROR, "Parse error"))

        if isinstance(payload, list):
            if not payload:
                return JSONResponse(
                    error_response(None, INVALID_REQUEST, "Invalid Request", "Empty batch")
                )
            responses = []
            for item in payload:
                response = await _handle_one(ctx, item)
                if response is not None:
                    responses.append(response)
            if not responses:
                return Response(status_code=204)
            return JSONResponse(responses)

        response = await _handle_one(ctx, payload)
        if response is None:
            return Response(status_code=204)
        return JSONResponse(response)
