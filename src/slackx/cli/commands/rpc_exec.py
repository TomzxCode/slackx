"""``slackx rpc exec`` command: run a CLI command on a running server."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter

from slackx.cli._internal._remote import run_remote
from slackx.cli._internal._shared import RpcTokenArg, RpcUrlArg, rpc_app

ArgsArg = Annotated[
    str,
    Parameter(
        allow_leading_hyphen=True,
        help="Command and arguments to run on the server. Put them after '--'.",
    ),
]


@rpc_app.command(name="exec")
async def exec_command(
    *args: ArgsArg,
    url: RpcUrlArg = None,
    token: RpcTokenArg = None,
) -> int:
    """Run any slackx command on the server and mirror its output and exit code.

    Put the remote command after '--' so its own flags are not parsed here:

        slackx rpc exec -- conversations get C1 --json

    Leading --url and --token options select the server; they can also come
    from SLACKX_RPC_URL and SLACKX_RPC_TOKEN.
    """
    return await run_remote(url, token, list(args))
