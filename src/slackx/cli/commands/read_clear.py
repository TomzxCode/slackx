"""``slackx read clear`` command."""

import sys

from slackx._log import get_logger
from slackx.cli._internal import _client
from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    ChannelIdArg,
    DbArg,
    LogLevelArg,
    ReaderArg,
    TsArg,
    WorkspaceArg,
    _setup,
    read_app,
)
from slackx.storage import delete_read_marker, delete_read_markers, transaction

log = get_logger(__name__)


@read_app.command(name="clear")
async def clear(
    *,
    reader: ReaderArg,
    channel: ChannelIdArg = None,
    ts: TsArg = None,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Delete stored last-read pointers for one reader.

    Deleting is scoped so a consumer can forget a channel without touching the
    rest: with --channel (and no --ts) every pointer for that channel is
    removed; with --channel and --ts just that thread's pointer is removed;
    with neither, every pointer owned by the reader is removed. Never calls
    Slack.
    """
    common = _setup(db, api_base_url, log_level, workspace)
    reader = reader.strip()
    if not reader:
        print("error: --reader must not be empty", file=sys.stderr)
        return 2

    if ts is not None and channel is None:
        print("error: --ts requires --channel", file=sys.stderr)
        return 2

    channel_id = channel
    if channel is not None:
        from slackx.cli._internal._channels import _resolve_channel

        resolved = await _resolve_channel(common, channel)
        if resolved is None:
            return 1
        channel_id = resolved

    async with _client._open_db(common) as conn:
        with transaction(conn):
            if channel_id is None:
                deleted = delete_read_markers(conn, reader)
            elif ts is None:
                deleted = delete_read_markers(conn, reader, channel=channel_id)
            else:
                deleted = delete_read_marker(conn, reader, channel_id, ts)

    print(f"deleted {deleted} read marker(s)", file=sys.stderr)
    return 0
