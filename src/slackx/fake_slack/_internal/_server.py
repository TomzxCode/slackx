"""HTTP server bootstrap for the fake Slack API."""

from http.server import HTTPServer

from slackx._log import get_logger
from slackx.fake_slack._internal._config import WorkspaceParams
from slackx.fake_slack._internal._handler import FakeSlackHandler
from slackx.fake_slack._internal._rate_limiter import RateLimiter
from slackx.fake_slack._internal._workspace import Workspace

log = get_logger(__name__)


def run_server(
    host: str = "127.0.0.1",
    port: int = 8199,
    params: WorkspaceParams | None = None,
) -> HTTPServer:
    workspace = Workspace(params=params)
    FakeSlackHandler.workspace = workspace
    FakeSlackHandler.rate_limiter = RateLimiter() if workspace.params.rate_limits else None
    server = HTTPServer((host, port), FakeSlackHandler)
    log.info(
        "fake_slack_server_starting",
        host=host,
        port=port,
        seed=workspace.params.seed,
        users=len(workspace.users),
        channels=len(workspace.channels),
        threads=len(workspace.threads),
        rate_limits=workspace.params.rate_limits,
    )
    return server
