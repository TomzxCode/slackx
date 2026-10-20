"""Remote execution: forward a CLI invocation to a running slackx server."""

from __future__ import annotations

import os
import sys

from slackx.rpc.protocol import DEFAULT_RPC_URL, RpcError

REMOTE_FLAG = "--remote"
REMOTE_TOKEN_FLAG = "--rpc-token"


def take_remote_args(args: list[str]) -> tuple[str | None, str | None, list[str]] | None:
    """Strip ``--remote`` and ``--rpc-token`` from the command line.

    Returns ``None`` when ``--remote`` is absent so the caller runs locally.
    The token flag is stripped only in remote mode, so a local command that
    happens to define the same flag still receives it.
    """
    if not any(arg == REMOTE_FLAG or arg.startswith(f"{REMOTE_FLAG}=") for arg in args):
        return None

    url = os.environ.get("SLACKX_RPC_URL") or None
    token = os.environ.get("SLACKX_RPC_TOKEN") or None
    rest: list[str] = []

    index = 0
    while index < len(args):
        arg = args[index]
        if arg == REMOTE_FLAG:
            if index + 1 < len(args) and looks_like_remote_url(args[index + 1]):
                url = args[index + 1]
                index += 1
        elif arg.startswith(f"{REMOTE_FLAG}="):
            url = arg.split("=", 1)[1]
        elif arg == REMOTE_TOKEN_FLAG:
            if index + 1 < len(args):
                token = args[index + 1]
                index += 1
        elif arg.startswith(f"{REMOTE_TOKEN_FLAG}="):
            token = arg.split("=", 1)[1]
        else:
            rest.append(arg)
        index += 1

    return url, token, rest


def looks_like_remote_url(value: str) -> bool:
    """Tell an explicit --remote address from the first command argument."""
    if "://" in value:
        return True
    host, separator, port = value.rpartition(":")
    return bool(separator and host and port.isdigit())


def read_piped_stdin() -> str:
    """Return piped standard input so commands that read it work remotely."""
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    try:
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


async def run_remote(url: str | None, token: str | None, args: list[str]) -> int:
    """Run ``args`` on the server, mirror its output and exit status."""
    from slackx.rpc.client import RpcClient, RpcTransportError

    if not args:
        print("error: no slackx command given", file=sys.stderr)
        return 1

    endpoint = url or os.environ.get("SLACKX_RPC_URL") or DEFAULT_RPC_URL
    token = token or os.environ.get("SLACKX_RPC_TOKEN") or None
    async with RpcClient(endpoint, token=token) as client:
        try:
            result = await client.exec(list(args), read_piped_stdin())
        except RpcError as exc:
            print(f"error: [{exc.code}] {exc.message}", file=sys.stderr)
            return 1
        except RpcTransportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    sys.stdout.write(str(result.get("stdout", "")))
    sys.stderr.write(str(result.get("stderr", "")))
    return int(result.get("exitCode", 0))
