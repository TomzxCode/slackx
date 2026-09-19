"""``slackx show-channels`` command."""

import sys

import structlog

from slack_cached.cli._internal import _client
from slack_cached.cli._internal._fields import (
    CHANNEL_DEFAULT_FIELDS,
    CHANNEL_FIELDS,
    parse_fields,
)
from slack_cached.cli._internal._refs import _output_format
from slack_cached.cli._internal._render import _render_channels_human, _render_channels_json
from slack_cached.cli._internal._shared import (
    ApiBaseUrlArg,
    ChannelFieldsArg,
    ChannelIdArg,
    DbArg,
    FetchArg,
    JsonArg,
    JsonlArg,
    LimitArg,
    LogLevelArg,
    WorkspaceArg,
    _setup,
    app,
)
from slack_cached.storage import get_channel, load_channel_display_names, load_channels

log = structlog.get_logger(__name__)


@app.command(name="show-channels")
async def show_channels(
    channel_id: ChannelIdArg = None,
    *,
    fetch: FetchArg = True,
    limit: LimitArg = 0,
    fields: ChannelFieldsArg = None,
    json_output: JsonArg = False,
    jsonl_output: JsonlArg = False,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Print cached channels to stdout (human-readable by default).

    Pass a channel id to show only that channel; it is fetched from Slack
    (via conversations.info) when not cached, unless --no-fetch is given.
    """
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)
    try:
        selected = parse_fields(fields, CHANNEL_FIELDS, CHANNEL_DEFAULT_FIELDS)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if channel_id is not None:
        from slack_cached.cli._internal._channels import _resolve_channel

        resolved = await _resolve_channel(common, channel_id)
        if resolved is None:
            return 1
        channel_id = resolved

    include_payload = bool({"is_private", "payload"} & set(selected))

    async with _client._open_db(common) as conn:
        channels = _load_selected(conn, channel_id, limit, include_payload)

    if channel_id is not None:
        if not channels and fetch:
            channels = await _fetch_single_channel(common, channel_id)
        if not channels:
            print(f"error: channel {channel_id} is not cached", file=sys.stderr)
            return 1
    elif not channels and fetch:
        from slack_cached.cache import fetch_channels

        log.info("channels_not_cached_fetching")
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            if not load_channels(conn, limit=1):
                await fetch_channels(conn, client)
            channels = load_channels(conn, limit=limit, include_payload=include_payload)

    display_names: dict[str, str] = {}
    if {"name", "display_name"} & set(selected):
        async with _client._open_db(common) as conn:
            display_names = load_channel_display_names(conn, [c.id for c in channels])

    if fmt in ("json", "jsonl"):
        sys.stdout.write(
            _render_channels_json(
                channels, display_names, selected, indent=2 if fmt == "json" else None
            )
        )
    else:
        sys.stdout.write(_render_channels_human(channels, display_names, selected))
    return 0


def _load_selected(conn, channel_id: str | None, limit: int, include_payload: bool):
    """Load one channel by id, or every cached channel when id is None."""
    if channel_id is None:
        return load_channels(conn, limit=limit, include_payload=include_payload)
    channel = get_channel(conn, channel_id)
    return [channel] if channel is not None else []


async def _fetch_single_channel(common, channel_id: str):
    """Fetch one channel's info from Slack, returning it on success."""
    import httpx

    from slack_cached.cache import fetch_channel
    from slack_cached.slack_api import SlackAPIError

    log.info("channel_not_cached_fetching", channel=channel_id)
    try:
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            channel = await fetch_channel(conn, client, channel_id)
    except (SlackAPIError, httpx.HTTPError) as exc:
        print(f"error: could not fetch channel {channel_id}: {exc}", file=sys.stderr)
        return []
    return [channel] if channel is not None else []
