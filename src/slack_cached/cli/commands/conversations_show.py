"""``slackx conversations show`` command."""

import sys
from typing import Annotated

import structlog
from cyclopts import Parameter

from slack_cached.cli._internal import _client
from slack_cached.cli._internal._duration import _oldest_ts_from_last
from slack_cached.cli._internal._format import _build_user_names, _format_ts
from slack_cached.cli._internal._refs import Target, _output_format, _resolve_target
from slack_cached.cli._internal._render import (
    _render_channel_human,
    _render_channel_json,
    _render_human,
    _render_json,
)
from slack_cached.cli._internal._shared import (
    ApiBaseUrlArg,
    CommonArgs,
    DbArg,
    FetchArg,
    JsonArg,
    JsonlArg,
    LogLevelArg,
    ReaderArg,
    TargetArg,
    TsArg,
    WithThreadMessageArg,
    WorkspaceArg,
    _setup,
    _timed,
    conversations_app,
)
from slack_cached.cli._internal._style import _supports_styles
from slack_cached.storage import (
    count_channel_messages,
    get_thread_state,
    latest_message_ts,
    load_channel_display_names,
    load_channel_messages,
    load_thread_messages,
    set_last_read,
    transaction,
)
from slack_cached.urls import ThreadRef

log = structlog.get_logger(__name__)


@conversations_app.command(name="show")
async def show(
    target: TargetArg = None,
    *,
    ts: TsArg = None,
    fetch: FetchArg = True,
    json_output: JsonArg = False,
    jsonl_output: JsonlArg = False,
    with_thread_message: WithThreadMessageArg = False,
    last: Annotated[
        str,
        Parameter(
            help="When showing a channel, limit history to the given lookback "
            "(e.g. 24h, 2d5h30m, 90m; default: 1d, use 'all' for full history).",
        ),
    ] = "1d",
    reader: ReaderArg = "default",
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Print a cached thread or channel to stdout (human-readable by default).

    Fetches first if not already cached (disable with --no-fetch).

    The target is a Slack permalink, a channel (id, name, or #name), or a DM
    (user id or @handle). Without --ts, shows the channel's messages; with --ts,
    shows that thread. Thread replies are omitted from channel output unless
    --with-thread-message is passed, in which case they are rendered marked as
    belonging to their thread.

    After printing, the --reader's read pointer for the shown channel or
    thread is advanced to the newest cached message, so showing is reading.
    Several consumers can read the same cache without affecting each other's
    pointers.
    """
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)

    resolved: Target | None = await _resolve_target(common, target, ts)
    if resolved is None:
        return 1

    if resolved.thread_ts is None:
        rc = await _show_channel(common, resolved.channel, fetch, last, fmt, with_thread_message)
        if rc == 0:
            await _mark_read(common, resolved.channel, None, reader)
        return rc

    log.debug("cmd_show_start")
    ref = ThreadRef(resolved.channel, resolved.thread_ts)

    # Read first from the offline-resolved workspace database; only hit the
    # network (and its auth.test-resolved workspace) on a cache miss.
    need_fetch = False
    async with _client._open_db(common) as conn:
        if get_thread_state(conn, ref.channel, ref.thread_ts) is not None or not fetch:
            messages, user_names, channel_name = _load_thread_view(conn, ref)
        else:
            need_fetch = True

    if need_fetch:
        # Imported lazily so the cached-read path does not pull in the
        # httpx-based Slack client (see _build_client).
        from slack_cached.cache import fetch_thread

        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            if get_thread_state(conn, ref.channel, ref.thread_ts) is None:
                log.info(
                    "thread_not_cached_fetching",
                    channel=ref.channel,
                    thread_ts=ref.thread_ts,
                    thread_ts_iso=_format_ts(ref.thread_ts),
                )
                if log_level == "debug":
                    print(
                        f"fetching thread {ref.channel}/{ref.thread_ts} from Slack...",
                        file=sys.stderr,
                    )
                await fetch_thread(conn, client, ref)
            messages, user_names, channel_name = _load_thread_view(conn, ref)

    log.debug("loaded_messages", count=len(messages))
    with _timed("render", format=fmt, messages=len(messages)):
        if fmt in ("json", "jsonl"):
            output = _render_json(
                ref,
                messages,
                user_names,
                channel_name,
                indent=2 if fmt == "json" else None,
            )
        else:
            output = _render_human(ref, messages, user_names, styled=_supports_styles(sys.stdout))
    with _timed("write_output", bytes=len(output)):
        sys.stdout.write(output)
        sys.stdout.flush()

    await _mark_read(common, ref.channel, ref.thread_ts, reader)
    return 0


async def _mark_read(
    common: CommonArgs,
    channel: str,
    thread_ts: str | None,
    reader: str,
) -> None:
    """Advance ``reader``'s read pointer to the newest cached message shown.

    Showing a channel or thread means the reader has read it, so the pointer is
    advanced after the output is written. Readers are independent, so this never
    moves another consumer's position. A blank reader or an empty scope (nothing
    cached) is left unmarked.
    """
    reader = reader.strip()
    if not reader:
        return
    async with _client._open_db(common) as conn:
        marker_ts = latest_message_ts(conn, channel, thread_ts)
        if marker_ts is None:
            return
        with transaction(conn):
            set_last_read(conn, reader, channel, marker_ts, thread_ts)
        log.debug(
            "read_marker_advanced",
            reader=reader,
            channel=channel,
            thread_ts=thread_ts,
            last_read_ts=marker_ts,
        )


def _load_thread_view(conn, ref) -> tuple[list, dict[str, str], str | None]:
    """Load a thread's messages plus resolved user/channel names from ``conn``."""
    messages = load_thread_messages(conn, ref.channel, ref.thread_ts)
    user_names = _build_user_names(conn, messages)
    channel_name = load_channel_display_names(conn, [ref.channel]).get(ref.channel)
    return messages, user_names, channel_name


async def _show_channel(
    common: CommonArgs,
    channel: str,
    fetch: bool,
    last: str,
    fmt: str,
    with_thread_message: bool = False,
) -> int:
    """Show all messages for a channel, fetching first if needed.

    By default only top-level messages are shown; ``with_thread_message``
    includes thread replies, each marked with its thread root.
    """
    oldest = _oldest_ts_from_last(last)

    # Read first from the offline-resolved workspace database; only hit the
    # network (and its auth.test-resolved workspace) on a cache miss.
    async with _client._open_db(common) as conn:
        messages = load_channel_messages(conn, channel, include_thread_replies=with_thread_message)
        user_names = _build_user_names(conn, messages)
        channel_name = load_channel_display_names(conn, [channel]).get(channel)

    if not messages and fetch:
        from slack_cached.cache import fetch_channel_messages

        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            if not count_channel_messages(conn, channel):
                log.info("channel_not_cached_fetching", channel=channel)
                if common.log_level == "debug":
                    print(
                        f"fetching messages for {channel} from Slack...",
                        file=sys.stderr,
                    )
                await fetch_channel_messages(conn, client, channel, oldest=oldest)
            messages = load_channel_messages(
                conn, channel, include_thread_replies=with_thread_message
            )
            user_names = _build_user_names(conn, messages)
            channel_name = load_channel_display_names(conn, [channel]).get(channel)

    with _timed("render", format=fmt, messages=len(messages)):
        if fmt in ("json", "jsonl"):
            output = _render_channel_json(
                channel,
                messages,
                user_names,
                channel_name,
                indent=2 if fmt == "json" else None,
            )
        else:
            output = _render_channel_human(
                channel,
                messages,
                user_names,
                channel_name,
                styled=_supports_styles(sys.stdout),
            )
    with _timed("write_output", bytes=len(output)):
        sys.stdout.write(output)
        sys.stdout.flush()
    return 0
