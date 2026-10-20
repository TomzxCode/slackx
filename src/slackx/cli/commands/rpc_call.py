"""``slackx rpc call`` command: call a running JSON-RPC server."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter

from slackx.cli._internal._shared import RpcTokenArg, RpcUrlArg, rpc_app
from slackx.rpc.protocol import DEFAULT_RPC_URL, RpcError

MethodArg = Annotated[
    str,
    Parameter(help="JSON-RPC method to call, for example users.list."),
]
ParamsJsonArg = Annotated[
    str | None,
    Parameter(
        help="JSON object of method parameters. Use '-' to read from stdin or "
        "'@path' to read from a file."
    ),
]
ParamsArg = Annotated[
    str | None,
    Parameter(
        name="--params",
        help="JSON object of method parameters (default: no parameters).",
    ),
]
ParamsFileArg = Annotated[
    Path | None,
    Parameter(
        name="--params-file",
        help="Read the JSON parameters from a file, or from stdin with '-'.",
    ),
]
CompactArg = Annotated[
    bool,
    Parameter(name="--compact", help="Print the result as one compact JSON line."),
]


@rpc_app.command(name="call")
async def call(
    method: MethodArg,
    params_json: ParamsJsonArg = None,
    *,
    params: ParamsArg = None,
    params_file: ParamsFileArg = None,
    url: RpcUrlArg = None,
    token: RpcTokenArg = None,
    compact: CompactArg = False,
) -> int:
    """Call a JSON-RPC method on a running slackx server and print the result.

    This lets a client use a server instance instead of running a CLI command
    per operation. The result is printed as JSON; JSON-RPC errors go to stderr
    and exit non-zero. Run 'slackx rpc methods' to list the available methods.

    Parameters can be passed as the second argument, as --params, or from a
    file with --params-file. Use '-' to read them from stdin.
    """
    from slackx.rpc.client import RpcClient, RpcTransportError

    try:
        payload = _load_params(params_json, params, params_file)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    endpoint = url or os.environ.get("SLACKX_RPC_URL") or DEFAULT_RPC_URL
    token = token or os.environ.get("SLACKX_RPC_TOKEN") or None
    async with RpcClient(endpoint, token=token) as client:
        try:
            result = await client.call(method, payload)
        except RpcError as exc:
            print(f"error: [{exc.code}] {exc.message}", file=sys.stderr)
            if exc.data is not None:
                print(json.dumps(exc.data, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        except RpcTransportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=None if compact else 2) + "\n")
    return 0


def _load_params(raw_json: str | None, raw: str | None, params_file: Path | None) -> dict:
    """Parse method parameters from the positional argument or the legacy flags."""
    supplied = [value for value in (raw_json, raw, params_file) if value is not None]
    if len(supplied) > 1:
        raise ValueError("use only one of the params argument, --params, or --params-file")

    if raw_json is not None:
        if raw_json == "-":
            text = sys.stdin.read()
        elif raw_json.startswith("@"):
            text = Path(raw_json[1:]).read_text()
        else:
            text = raw_json
    elif params_file is not None:
        text = sys.stdin.read() if str(params_file) == "-" else params_file.read_text()
    else:
        text = raw or ""

    if not text.strip():
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"parameters are not valid JSON: {exc}") from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("parameters must be a JSON object")
    return value
