"""``slackx rpc methods`` command: list a running server's JSON-RPC methods."""

from __future__ import annotations

import json
import os
import sys
from typing import Annotated

from cyclopts import Parameter

from slackx.cli._internal._shared import rpc_app
from slackx.rpc.protocol import DEFAULT_RPC_URL, RpcError

UrlArg = Annotated[
    str | None,
    Parameter(
        name=["--url", "--server"],
        help="JSON-RPC endpoint (default: SLACKX_RPC_URL, then http://127.0.0.1:8280/rpc).",
    ),
]
JsonArg = Annotated[
    bool,
    Parameter(name="--json", help="Print the method catalog as JSON."),
]


@rpc_app.command(name="methods")
async def methods(*, url: UrlArg = None, json_output: JsonArg = False) -> int:
    """List the methods a running slackx server exposes."""
    from slackx.rpc.client import RpcClient, RpcTransportError

    endpoint = url or os.environ.get("SLACKX_RPC_URL") or DEFAULT_RPC_URL
    async with RpcClient(endpoint) as client:
        try:
            catalog = await client.methods()
        except RpcError as exc:
            print(f"error: [{exc.code}] {exc.message}", file=sys.stderr)
            return 1
        except RpcTransportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if json_output:
        sys.stdout.write(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
        return 0

    for entry in catalog:
        name = entry.get("name", "?")
        params = entry.get("params") or []
        signature = f"{name}({', '.join(params)})" if params else name
        description = entry.get("description") or ""
        sys.stdout.write(f"{signature}\n    {description}\n")
    return 0
