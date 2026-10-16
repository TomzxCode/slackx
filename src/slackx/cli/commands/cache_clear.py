"""``slackx cache clear`` command."""

import sys
from typing import Annotated, Literal

from cyclopts import Parameter

from slackx.cli._internal import _client
from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    DbArg,
    LogLevelArg,
    WorkspaceArg,
    _setup,
    cache_app,
)
from slackx.storage import clear_cache

ClearTarget = Literal["all", "messages", "channels", "users", "read"]


@cache_app.command(name="clear")
async def clear(
    target: Annotated[
        ClearTarget,
        Parameter(help="What to clear: all (default), messages, channels, users, or read."),
    ] = "all",
    *,
    yes: Annotated[
        bool,
        Parameter(name=["--yes", "-y"], help="Skip the confirmation prompt."),
    ] = False,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Delete cached data: everything, messages, channels, users, or read markers.

    Reads and clears the cache database directly; never calls Slack. Clearing
    messages also clears their thread metadata, so the threads are refetched on
    next use. Without --yes the command asks for confirmation (interactive
    terminals only).
    """
    common = _setup(db, api_base_url, log_level, workspace)

    if not yes and not _confirm(target):
        return 1

    async with _client._open_db(common) as conn:
        cleared = clear_cache(
            conn,
            messages=target in ("all", "messages"),
            channels=target in ("all", "channels"),
            users=target in ("all", "users"),
            read_markers=target in ("all", "read"),
        )

    print(
        f"cleared messages={cleared.messages} threads={cleared.threads} "
        f"channels={cleared.channels} users={cleared.users} "
        f"read_markers={cleared.read_markers}",
        file=sys.stderr,
    )
    return 0


def _confirm(target: str) -> bool:
    """Ask before deleting; --yes bypasses this, and a non-tty aborts."""
    if not sys.stdin.isatty():
        print(
            "refusing to clear the cache without confirmation; pass --yes to proceed",
            file=sys.stderr,
        )
        return False
    print(
        f"Clear cached {target}? This cannot be undone. [y/N] ",
        end="",
        file=sys.stderr,
        flush=True,
    )
    return sys.stdin.readline().strip().lower() in ("y", "yes")
