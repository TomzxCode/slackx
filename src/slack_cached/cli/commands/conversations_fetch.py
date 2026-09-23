"""``slackx conversations fetch`` command."""

import sys
from typing import Annotated

import structlog
from cyclopts import Parameter

from slack_cached.cli._internal import _client
from slack_cached.cli._internal._duration import _oldest_ts_from_last
from slack_cached.cli._internal._refs import Target, _resolve_target
from slack_cached.cli._internal._shared import (
    ApiBaseUrlArg,
    CommonArgs,
    DbArg,
    LogLevelArg,
    TargetArg,
    TsArg,
    WorkspaceArg,
    _setup,
    conversations_app,
)
from slack_cached.urls import ThreadRef

log = structlog.get_logger(__name__)


@conversations_app.command(name="fetch")
async def fetch(
    target: TargetArg = None,
    *,
    ts: TsArg = None,
    full_threads: Annotated[
        bool,
        Parameter(help="When fetching a channel, also fetch all replies for every thread."),
    ] = False,
    last: Annotated[
        str,
        Parameter(
            help="When fetching a channel, limit history to the given lookback "
            "(e.g. 24h, 2d5h30m, 90m; default: 1d, use 'all' for full history).",
        ),
    ] = "1d",
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Cache or refresh a Slack thread, or fetch all messages from a channel or DM.

    The target is a Slack permalink, a channel (id, name, or #name), or a DM
    (user id or @handle). Without --ts, fetches the channel's messages; with
    --ts, fetches that thread.
    """
    common = _setup(db, api_base_url, log_level, workspace)

    resolved: Target | None = await _resolve_target(common, target, ts)
    if resolved is None:
        return 1
    if resolved.thread_ts is None:
        return await _fetch_channel_messages(common, resolved.channel, full_threads, last)

    from slack_cached.cache import fetch_thread

    ref = ThreadRef(resolved.channel, resolved.thread_ts)
    async with _client._open_client(common) as client, _client._open_db(common, client) as conn:
        result = await fetch_thread(conn, client, ref)
    print(
        f"cached {result.total_messages} messages "
        f"({result.fetched_messages} new/updated, "
        f"{'incremental' if result.incremental else 'full'}) "
        f"for {result.channel}/{result.thread_ts}",
        file=sys.stderr,
    )
    return 0


async def _fetch_channel_messages(
    common: CommonArgs, channel: str, full_threads: bool, last: str
) -> int:
    """Fetch messages from a channel."""
    from slack_cached.cache import fetch_channel_messages

    oldest = _oldest_ts_from_last(last)
    async with _client._open_client(common) as client, _client._open_db(common, client) as conn:
        result = await fetch_channel_messages(
            conn, client, channel, full_threads=full_threads, oldest=oldest
        )
    detail = (
        f", {result.threads_with_replies_fetched} threads with replies fetched"
        if full_threads
        else ""
    )
    print(
        f"cached {result.total_messages} messages for {result.channel} "
        f"({result.fetched_messages} fetched{detail})",
        file=sys.stderr,
    )
    return 0
