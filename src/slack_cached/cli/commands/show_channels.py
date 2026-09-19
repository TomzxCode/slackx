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
from slack_cached.storage import load_channel_display_names, load_channels

log = structlog.get_logger(__name__)


@app.command(name="show-channels")
async def show_channels(
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
    """Print cached channels to stdout (human-readable by default)."""
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)
    try:
        selected = parse_fields(fields, CHANNEL_FIELDS, CHANNEL_DEFAULT_FIELDS)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    async with _client._open_db(common) as conn:
        channels = load_channels(conn)

    if not channels and fetch:
        from slack_cached.cache import fetch_channels

        log.info("channels_not_cached_fetching")
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            if not load_channels(conn):
                await fetch_channels(conn, client)
            channels = load_channels(conn)

    if limit > 0:
        channels = channels[:limit]

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
