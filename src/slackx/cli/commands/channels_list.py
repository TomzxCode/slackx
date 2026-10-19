"""``slackx channels list`` command."""

import sys

from slackx._log import get_logger
from slackx.cli._internal import _client
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
    DbArg,
    FetchArg,
    JsonArg,
    JsonlArg,
    LimitArg,
    LogLevelArg,
    WorkspaceArg,
    _setup,
    channels_app,
)
from slackx.cli._internal._style import _supports_styles
from slackx.storage import load_channel_display_names, load_channels

log = get_logger(__name__)


@channels_app.command(name="list")
async def list_channels(
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

    Every cached channel is listed; use 'channels get' for a single channel.
    """
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)
    try:
        selected = parse_fields(fields, CHANNEL_FIELDS, CHANNEL_DEFAULT_FIELDS)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    include_payload = bool({"is_private", "payload"} & set(selected))

    async with _client._open_db(common) as conn:
        channels = load_channels(conn, limit=limit, include_payload=include_payload)

    if not channels and fetch:
        from slackx.cache import fetch_channels

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
        sys.stdout.write(
            _render_channels_human(
                channels, display_names, selected, styled=_supports_styles(sys.stdout)
            )
        )
    return 0
