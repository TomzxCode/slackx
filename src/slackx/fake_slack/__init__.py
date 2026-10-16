"""Fake Slack API server package.

Provides a deterministic, in-process Slack Web API implementation backed by
generated workspace data.  Importing this package registers the ``run``
command and re-exports the public API.
"""

from collections.abc import Sequence

from slackx.fake_slack._internal._config import (
    WorkspaceParams,
    _parse_epoch_base,
    _parse_range_flag,
)
from slackx.fake_slack._internal._constants import DEFAULT_EPOCH_BASE, ENDPOINT_RATE_LIMITS
from slackx.fake_slack._internal._handler import FakeSlackHandler
from slackx.fake_slack._internal._rate_limiter import RateLimiter
from slackx.fake_slack._internal._server import run_server
from slackx.fake_slack._internal._workspace import Workspace
from slackx.fake_slack.commands import run  # noqa: F401
from slackx.fake_slack.commands.run import fake_server_app

__all__ = (
    "DEFAULT_EPOCH_BASE",
    "ENDPOINT_RATE_LIMITS",
    "FakeSlackHandler",
    "RateLimiter",
    "Workspace",
    "WorkspaceParams",
    "_parse_epoch_base",
    "_parse_range_flag",
    "fake_server_app",
    "main",
    "run_server",
)


def main(argv: Sequence[str] | None = None) -> int:
    return fake_server_app(argv, result_action="return_int_as_exit_code_else_zero")
