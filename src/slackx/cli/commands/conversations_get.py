"""``slackx conversations get`` command (alias: show)."""

import sys
from typing import Annotated

from cyclopts import Parameter

from slackx._log import get_logger
from slackx.cli._internal import _client
from slackx.cli._internal._duration import _oldest_ts_from_last
from slackx.cli._internal._format import _build_user_names, _format_ts
from slackx.cli._internal._refs import Target, _output_format, _resolve_target
from slackx.cli._internal._render import (
    _render_channel_human,
    _render_channel_json,
    _render_human,
    _render_json,
)
from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    CommonArgs,
    DbArg,
    JsonArg,
    JsonlArg,
    LogLevelArg,
    ReaderArg,
    ShowFetchArg,
    TargetArg,
    TsArg,
    WithThreadMessageArg,
    WorkspaceArg,
    _setup,
    _timed,
    conversations_app,
)
from slackx.cli._internal._style import _supports_styles
from slackx.storage import (
    count_channel_messages,
    get_thread_state,
    latest_message_ts,
    load_channel_display_names,
    load_channel_messages,
    load_thread_messages,
    set_last_read,
    transaction,
)
from slackx.urls import ThreadRef

log = get_logger(__name__)


@conversations_app.command(name="get", alias="show")
async def get(
    target: TargetArg = None,
    *,
    ts: TsArg = None,
    fetch: ShowFetchArg = None,
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

    Fetches first if not already cached. --fetch forces a refresh even when
    cached; --no-fetch never fetches the target (resolving a channel by name
    still fetches the channel list when the cache is empty).

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
    # network (and its auth.test-resolved workspace) on a cache miss or an
    # explicit --fetch refresh.
    need_fetch = False
    cached = False
    async with _client._open_db(common) as conn:
        cached = get_thread_state(conn, ref.channel, ref.thread_ts) is not None
        if _should_fetch(fetch, cached):
            need_fetch = True
        else:
            messages, user_names, channel_name = _load_thread_view(conn, ref)

    if need_fetch:
        # Imported lazily so the cached-read path does not pull in the
        # httpx-based Slack client (see _build_client).
        from slackx.cache import fetch_thread

        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            # An explicit --fetch always refreshes; the default only fetches
            # when the thread is still missing (re-checked here in case another
            # process cached it in the meantime).
            if fetch is True or get_thread_state(conn, ref.channel, ref.thread_ts) is None:
                if not cached:
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


def _should_fetch(fetch: bool | None, cached: bool) -> bool:
    """Decide whether to hit Slack given the --fetch flag and cache state.

    ``--fetch`` (True) always fetches, ``--no-fetch`` (False) never does, and
    the default (None) fetches only when the target is not cached.
    """
    if fetch is None:
        return not cached
    return fetch


async def _show_channel(
    common: CommonArgs,
    channel: str,
    fetch: bool | None,
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
    # network (and its auth.test-resolved workspace) on a cache miss or an
    # explicit --fetch refresh.
    need_fetch = False
    cached = False
    messages: list = []
    user_names: dict[str, str] = {}
    channel_name: str | None = None
    async with _client._open_db(common) as conn:
        cached = count_channel_messages(conn, channel) > 0
        if _should_fetch(fetch, cached):
            need_fetch = True
        else:
            messages = load_channel_messages(
                conn, channel, include_thread_replies=with_thread_message
            )
            user_names = _build_user_names(conn, messages)
            channel_name = load_channel_display_names(conn, [channel]).get(channel)

    if need_fetch:
        from slackx.cache import fetch_channel_messages

        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            # An explicit --fetch always refreshes; the default only fetches
            # when the channel is still empty (re-checked here in case another
            # process cached it in the meantime).
            if fetch is True or not count_channel_messages(conn, channel):
                if not cached:
                    log.info("channel_not_cached_fetching", channel=channel)
                    if common.log_level == "debug":
                        print(
                            f"fetching messages for {channel} from Slack...",
                            file=sys.stderr,
                        )
                await fetch_channel_messages(
                    conn,
                    client,
                    channel,
                    full_threads=with_thread_message,
                    oldest=oldest,
                )
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
