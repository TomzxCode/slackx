"""Command-line interface for slackx.

Subcommands:
- conversations fetch: cache or refresh a Slack thread silently.
- conversations show: print a cached thread to stdout (human-readable by default, --json for JSON).
- conversations search: search Slack and cache the matches.
- conversations poll: poll channels in a loop for new messages.
- serve: browse the cache through a local web UI.
"""

from collections.abc import Sequence

from slack_cached.cli._internal._shared import app

# Import command modules so their @app.command decorators register them.
from slack_cached.cli.commands import (  # noqa: F401
    cache_clear,
    cache_status,
    channels_fetch,
    channels_list,
    conversations_fetch,
    conversations_poll,
    conversations_search,
    conversations_show,
    serve,
    users_fetch,
    users_list,
)

__all__ = ["app", "main"]


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by tests and the ``slackx`` console script."""
    return app(argv, result_action="return_int_as_exit_code_else_zero")


if __name__ == "__main__":
    raise SystemExit(main())
