"""Command-line interface for slackx.

Subcommands:
- conversations fetch: cache or refresh a Slack thread silently.
- conversations get (alias: show): print a cached thread to stdout
  (human-readable by default, --json for JSON); also advances the last-read
  pointer for the shown channel or thread.
- conversations search: search Slack and cache the matches.
- conversations poll: poll channels in a loop for new messages.
- conversations read mark/show/clear: track per-consumer last-read pointers.
- cache status/clear: inspect and manage the local cache.
- rpc serve/call/methods: serve the JSON-RPC API or call a running server.
- serve: browse the cache through a local web UI (and the JSON-RPC endpoint).
"""

from collections.abc import Sequence

from slackx.cli._internal._shared import app

# Import command modules so their @app.command decorators register them.
from slackx.cli.commands import (  # noqa: F401
    cache_clear,
    cache_status,
    channels_fetch,
    channels_get,
    channels_list,
    conversations_fetch,
    conversations_get,
    conversations_poll,
    conversations_search,
    read_clear,
    read_mark,
    read_show,
    rpc_call,
    rpc_methods,
    rpc_serve,
    serve,
    users_fetch,
    users_get,
    users_list,
)

__all__ = ["app", "main"]


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by tests and the ``slackx`` console script."""
    return app(argv, result_action="return_int_as_exit_code_else_zero")


if __name__ == "__main__":
    raise SystemExit(main())
