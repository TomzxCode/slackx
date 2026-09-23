"""``slackx channels fetch`` command."""

import sys

from slack_cached.cli._internal import _client
from slack_cached.cli._internal._shared import (
    ApiBaseUrlArg,
    ChannelIdArg,
    DbArg,
    LogLevelArg,
    WorkspaceArg,
    _setup,
    channels_app,
)


@channels_app.command(name="fetch")
async def fetch(
    channel_id: ChannelIdArg = None,
    *,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Fetch and cache every visible channel, or a single channel by id."""
    common = _setup(db, api_base_url, log_level, workspace)

    if channel_id is not None:
        return await _fetch_one_channel(common, channel_id)

    from slack_cached.cache import fetch_channels

    async with _client._open_client(common) as client, _client._open_db(common, client) as conn:
        result = await fetch_channels(conn, client)
    print(
        f"processed {result.processed} channels ({result.added} added, {result.total} total in db)",
        file=sys.stderr,
    )
    return 0


async def _fetch_one_channel(common, channel_id: str) -> int:
    """Fetch and cache a single channel via conversations.info."""
    import httpx

    from slack_cached.cache import fetch_channel
    from slack_cached.cli._internal._channels import _resolve_channel
    from slack_cached.slack_api import SlackAPIError

    resolved = await _resolve_channel(common, channel_id)
    if resolved is None:
        return 1

    try:
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            channel = await fetch_channel(conn, client, resolved)
    except (SlackAPIError, httpx.HTTPError) as exc:
        print(f"error: could not fetch channel {resolved}: {exc}", file=sys.stderr)
        return 1

    if channel is None:
        print(f"error: channel {resolved} not found", file=sys.stderr)
        return 1
    label = channel.name or resolved
    print(f"fetched channel {resolved} ({label})", file=sys.stderr)
    return 0
