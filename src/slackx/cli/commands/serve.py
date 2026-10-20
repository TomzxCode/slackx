"""``slackx serve`` command: browse the cache in a browser."""

from __future__ import annotations

import os
import sys
from typing import Annotated

from cyclopts import Parameter

from slackx._log import get_logger
from slackx.cli._internal import _client
from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    DbArg,
    LogLevelArg,
    ServeRpcAllowExecArg,
    ServeRpcTokenArg,
    WorkspaceArg,
    _setup,
    app,
    is_loopback_host,
)

log = get_logger(__name__)

HostArg = Annotated[
    str,
    Parameter(help="Interface to bind the web server to."),
]
PortArg = Annotated[
    int,
    Parameter(help="Port to bind the web server to."),
]


@app.command(name="serve")
def serve(
    *,
    host: HostArg = "127.0.0.1",
    port: PortArg = 8280,
    token: ServeRpcTokenArg = None,
    allow_exec: ServeRpcAllowExecArg = True,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Serve the cached database through a local web UI and the JSON-RPC API.

    Opens a Slack-like interface to browse cached users, channels, messages
    and threads. Ctrl+P opens a palette to jump between channels.
    Refresh buttons trigger live Slack fetches when
    credentials are configured. Without --db or --workspace, the workspace
    is determined from the configured token/cookie (cached on disk after the
    first auth.test), falling back to the last-used workspace offline.

    The JSON-RPC endpoint is POST /rpc. Binding a non-loopback host requires
    --rpc-token, because clients can modify the cache and run CLI commands.
    """
    token = token or os.environ.get("SLACKX_RPC_TOKEN") or None
    if token is None and not is_loopback_host(host):
        print(
            f"error: refusing to expose the JSON-RPC API on {host} without --token: "
            "clients could run CLI commands and change the cache",
            file=sys.stderr,
        )
        return 1

    common = _setup(db, api_base_url, log_level, workspace)
    db_path = _client._resolve_db_path_sync(common)

    import uvicorn

    from slackx.server.app import create_app

    webapp = create_app(
        db_path=db_path,
        api_base_url=common.api_base_url,
        log_level=log_level,
        rpc_token=token,
        rpc_allow_exec=allow_exec,
    )
    log.info("serve_starting", host=host, port=port, db_path=str(db_path))
    if token:
        print("Bearer token authentication is required for JSON-RPC.")
    if allow_exec:
        print("cli.run is enabled: clients can execute slackx commands on this server.")
    uvicorn.run(webapp, host=host, port=port, log_level=common.log_level)
    return 0
