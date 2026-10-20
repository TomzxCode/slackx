"""``slackx rpc methods`` command: list a running server's JSON-RPC methods."""

from __future__ import annotations

import json
import os
import sys
from typing import Annotated

from cyclopts import Parameter

from slackx.cli._internal._shared import RpcTokenArg, RpcUrlArg, rpc_app
from slackx.rpc.protocol import DEFAULT_RPC_URL, RpcError

JsonArg = Annotated[
    bool,
    Parameter(name="--json", help="Print the method catalog as JSON."),
]


@rpc_app.command(name="methods")
async def methods(
    *,
    url: RpcUrlArg = None,
    token: RpcTokenArg = None,
    json_output: JsonArg = False,
) -> int:
    """List the methods a running slackx server exposes."""
    from slackx.rpc.client import RpcClient, RpcTransportError

    endpoint = url or os.environ.get("SLACKX_RPC_URL") or DEFAULT_RPC_URL
    token = token or os.environ.get("SLACKX_RPC_TOKEN") or None
    async with RpcClient(endpoint, token=token) as client:
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

    if not catalog:
        sys.stdout.write("No methods exposed.\n")
        return 0

    rows = [(str(entry.get("name", "?")), str(entry.get("description") or "")) for entry in catalog]
    width = max(len("METHOD"), *(len(name) for name, _ in rows))
    sys.stdout.write(f"{'METHOD':<{width}}  DESCRIPTION\n")
    for name, description in rows:
        sys.stdout.write(f"{name:<{width}}  {description}\n")
    return 0
