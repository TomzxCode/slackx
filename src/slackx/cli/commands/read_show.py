"""``slackx read show`` command."""

import json
import sys
from dataclasses import asdict

import structlog

from slackx.cli._internal import _client
from slackx.cli._internal._refs import _output_format
from slackx.cli._internal._render import _render_read_markers_human
from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    ChannelIdArg,
    DbArg,
    JsonArg,
    JsonlArg,
    LogLevelArg,
    OptionalReaderArg,
    WorkspaceArg,
    _setup,
    read_app,
)
from slackx.cli._internal._style import _supports_styles
from slackx.storage import load_read_markers

log = structlog.get_logger(__name__)


@read_app.command(name="show")
async def show(
    *,
    reader: OptionalReaderArg = None,
    channel: ChannelIdArg = None,
    json_output: JsonArg = False,
    jsonl_output: JsonlArg = False,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Print stored last-read pointers (human-readable by default).

    With --reader only that reader's pointers are shown; otherwise every
    reader's are. --channel limits output to one channel (id, name, or #name).
    Never calls Slack.
    """
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)

    channel_id = channel
    if channel is not None:
        from slackx.cli._internal._channels import _resolve_channel

        resolved = await _resolve_channel(common, channel)
        if resolved is None:
            return 1
        channel_id = resolved

    async with _client._open_db(common) as conn:
        markers = load_read_markers(conn, reader, channel=channel_id)

    if fmt in ("json", "jsonl"):
        payload = {
            "read_count": len(markers),
            "markers": [asdict(marker) for marker in markers],
        }
        sys.stdout.write(
            json.dumps(payload, ensure_ascii=False, indent=2 if fmt == "json" else None) + "\n"
        )
    else:
        sys.stdout.write(_render_read_markers_human(markers, styled=_supports_styles(sys.stdout)))
    return 0
