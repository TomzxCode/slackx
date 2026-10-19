"""``slackx rpc serve`` command: serve the JSON-RPC API."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter

from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    DbArg,
    LogLevelArg,
    WorkspaceArg,
    rpc_app,
)

HostArg = Annotated[
    str,
    Parameter(help="Interface to bind the server to."),
]
PortArg = Annotated[
    int,
    Parameter(help="Port to bind the server to."),
]


@rpc_app.command(name="serve")
def serve(
    *,
    host: HostArg = "127.0.0.1",
    port: PortArg = 8280,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Serve the JSON-RPC API (and the web UI) on a local HTTP port.

    The JSON-RPC endpoint is POST /rpc on the same server as the web UI.
    Point clients at http://HOST:PORT/rpc, or call them with
    'slackx rpc call METHOD --url http://HOST:PORT/rpc'.
    """
    from slackx.cli.commands.serve import serve as serve_web

    return serve_web(
        host=host,
        port=port,
        db=db,
        workspace=workspace,
        api_base_url=api_base_url,
        log_level=log_level,
    )
