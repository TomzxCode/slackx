"""``slackx channels get`` command (alias: show)."""

import sys

from slackx._log import get_logger
from slackx.cli._internal import _client
from slackx.cli._internal._channels import _resolve_channel
from slackx.cli._internal._fields import (
    CHANNEL_DEFAULT_FIELDS,
    CHANNEL_FIELDS,
    parse_fields,
)
from slackx.cli._internal._refs import _output_format
from slackx.cli._internal._render import _render_channels_human, _render_channels_json
from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    ChannelFieldsArg,
    ChannelTargetArg,
    DbArg,
    GetFetchArg,
    JsonArg,
    JsonlArg,
    LogLevelArg,
    WorkspaceArg,
    _setup,
    channels_app,
)
from slackx.cli._internal._style import _supports_styles
from slackx.storage import CachedChannel, get_channel, load_channel_display_names

log = get_logger(__name__)


@channels_app.command(name="get", alias="show")
async def get(
    channel: ChannelTargetArg,
    *,
    fetch: GetFetchArg = True,
    fields: ChannelFieldsArg = None,
    json_output: JsonArg = False,
    jsonl_output: JsonlArg = False,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Print one cached channel, fetching it from Slack when missing.

    CHANNEL is a channel id (e.g. C001), a bare name (e.g. general), or a
    '#'-prefixed name (e.g. #general). A cache miss fetches just that channel
    via conversations.info unless --no-fetch is given.
    """
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)
    try:
        selected = parse_fields(fields, CHANNEL_FIELDS, CHANNEL_DEFAULT_FIELDS)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    resolved = await _resolve_channel(common, channel)
    if resolved is None:
        return 1

    async with _client._open_db(common) as conn:
        cached = get_channel(conn, resolved)

    if cached is None and fetch:
        cached = await _fetch_single_channel(common, resolved)
    if cached is None:
        print(f"error: channel {resolved} is not cached", file=sys.stderr)
        return 1

    display_names: dict[str, str] = {}
    if {"name", "display_name"} & set(selected):
        async with _client._open_db(common) as conn:
            display_names = load_channel_display_names(conn, [resolved])

    channels = [cached]
    if fmt in ("json", "jsonl"):
        sys.stdout.write(
            _render_channels_json(
                channels, display_names, selected, indent=2 if fmt == "json" else None
            )
        )
    else:
        sys.stdout.write(
            _render_channels_human(
                channels, display_names, selected, styled=_supports_styles(sys.stdout)
            )
        )
    return 0


async def _fetch_single_channel(common, channel_id: str) -> CachedChannel | None:
    """Fetch one channel's info from Slack, returning it on success."""
    import httpx

    from slackx.cache import fetch_channel
    from slackx.slack_api import SlackAPIError

    log.info("channel_not_cached_fetching", channel=channel_id)
    try:
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            return await fetch_channel(conn, client, channel_id)
    except (SlackAPIError, httpx.HTTPError) as exc:
        print(f"error: could not fetch channel {channel_id}: {exc}", file=sys.stderr)
        return None
