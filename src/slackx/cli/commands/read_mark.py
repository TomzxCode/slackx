"""``slackx read mark`` command."""

import sys

from slackx._log import get_logger
from slackx.cli._internal import _client
from slackx.cli._internal._refs import _resolve_target
from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    DbArg,
    LastReadArg,
    LogLevelArg,
    ReaderArg,
    TargetArg,
    TsArg,
    WorkspaceArg,
    _setup,
    read_app,
)
from slackx.storage import latest_message_ts, set_last_read, transaction

log = get_logger(__name__)


@read_app.command(name="mark")
async def mark(
    target: TargetArg = None,
    *,
    ts: TsArg = None,
    reader: ReaderArg = "default",
    last_read: LastReadArg = None,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Record that a reader has read a channel or thread up to a message.

    TARGET is a Slack permalink, a channel (id, name, or #name), or a DM (user
    id or @handle). Without --ts the channel-level pointer is advanced; with
    --ts the pointer for that thread is advanced. The pointer value defaults to
    the newest cached message in scope; pass --last-read to set it explicitly.

    Pointers are namespaced by --reader, so several consumers (a web UI, a
    poll watcher, ad-hoc scripts) each keep their own last-read position over
    the same cache.
    """
    common = _setup(db, api_base_url, log_level, workspace)
    reader = reader.strip()
    if not reader:
        print("error: --reader must not be empty", file=sys.stderr)
        return 2

    resolved = await _resolve_target(common, target, ts)
    if resolved is None:
        return 1

    async with _client._open_db(common) as conn:
        marker_ts = last_read
        if marker_ts is None:
            marker_ts = latest_message_ts(conn, resolved.channel, resolved.thread_ts)
        if marker_ts is None:
            scope = (
                f"thread {resolved.channel}/{resolved.thread_ts}"
                if resolved.thread_ts is not None
                else f"channel {resolved.channel}"
            )
            print(
                f"error: no cached messages in {scope}; fetch first or pass --last-read",
                file=sys.stderr,
            )
            return 1
        with transaction(conn):
            marker = set_last_read(conn, reader, resolved.channel, marker_ts, resolved.thread_ts)

    scope = (
        f"thread {marker.channel}/{marker.thread_ts}"
        if marker.thread_ts is not None
        else f"channel {marker.channel}"
    )
    print(
        f"marked {reader!r} read in {scope} up to {marker.last_read_ts}",
        file=sys.stderr,
    )
    return 0
