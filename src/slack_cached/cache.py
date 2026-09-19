"""High-level async cache operations for slackx.

``fetch_thread`` decides whether to do a full or incremental fetch based on
existing cache state, calls the Slack API concurrently, and writes the results
back to SQLite. SQLite writes remain synchronous since they are fast and
happen within a single event loop.

``load_thread`` reads a cached thread back out for display (pure DB read).
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from .slack_api import DEFAULT_SEARCH_LIMIT, SlackClient
from .storage import (
    CachedChannel,
    CachedMessage,
    CachedUser,
    count_channel_messages,
    count_channels,
    count_messages,
    count_users,
    get_channel,
    get_thread_state,
    get_user,
    load_thread_messages,
    record_thread_refresh,
    transaction,
    upsert_channels,
    upsert_messages,
    upsert_users,
)
from .urls import ThreadRef

log = structlog.get_logger(__name__)


def _ts_to_iso(ts: str | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


def _normalize_channel_id(channel: Any) -> str | None:
    """Return a bare channel id from a search match's ``channel`` field.

    ``conversations.history``/``replies`` return ``channel`` as a bare id
    string, but ``search.messages`` returns it as an object
    (``{"id", "name", ...}``). Accept either and return the id, or None when it
    cannot be determined.
    """
    if isinstance(channel, dict):
        cid = channel.get("id")
        return cid if isinstance(cid, str) and cid else None
    if isinstance(channel, str):
        return channel or None
    return None


def _latest_ts(messages: list[dict[str, Any]]) -> str | None:
    """Return the highest 'ts' in messages, treated as a float, or None."""
    best: tuple[float, str] | None = None
    for msg in messages:
        ts = msg.get("ts")
        if not ts:
            continue
        try:
            value = float(ts)
        except (TypeError, ValueError):
            continue
        if best is None or value > best[0]:
            best = (value, ts)
    return best[1] if best else None


@dataclass(frozen=True)
class FetchResult:
    """Summary of what ``fetch_thread`` did."""

    channel: str
    thread_ts: str
    fetched_messages: int
    total_messages: int
    incremental: bool


@dataclass(frozen=True)
class ListFetchResult:
    """Summary of a bulk fetch of users or channels.

    ``processed`` is how many records were received from Slack and written.
    ``added`` is how many of those were new rows in the database (the rest were
    updates to existing rows). ``total`` is the row count after the fetch.
    """

    processed: int
    added: int
    total: int


@dataclass(frozen=True)
class ChannelFetchResult:
    """Summary of what ``fetch_channel_messages`` did."""

    channel: str
    fetched_messages: int
    total_messages: int
    threads_with_replies_fetched: int


@dataclass(frozen=True)
class SearchFetchResult:
    """Summary of what ``fetch_search`` did.

    ``matches`` is the raw list of search matches (each carrying its own
    ``channel``, ``ts`` and ``permalink``) so the caller can render them
    without re-reading the cache.

    Threads: ``threads_seen`` is every distinct thread touched on this run;
    ``threads_new`` is the subset that received at least one newly inserted
    or modified message. The difference is the threads whose contents were
    already current in the cache.

    Messages: ``messages_seen`` is every message passed to the cache (matches
    in default mode, matches plus replies in ``--full-threads`` mode);
    ``messages_new`` is the subset actually written. The difference is the
    messages that were already current.
    """

    query: str
    matches: list[dict[str, Any]]
    threads_seen: int
    threads_new: int
    messages_seen: int
    messages_new: int


async def fetch_thread(
    conn: sqlite3.Connection,
    client: SlackClient,
    ref: ThreadRef,
) -> FetchResult:
    """Fetch a thread from Slack, doing an incremental refresh when possible.

    Strategy:
    - If the thread is not cached, fetch all messages from Slack.
    - If the thread is cached, ask Slack for replies with oldest=latest_reply.
      That call returns any new replies plus possibly an edit of an older one;
      we upsert by ts so edits overwrite stale rows.
    """
    state = get_thread_state(conn, ref.channel, ref.thread_ts)
    incremental = state is not None and state.latest_reply is not None
    oldest = state.latest_reply if incremental else None

    log.info(
        "fetch_thread_start",
        channel=ref.channel,
        thread_ts=ref.thread_ts,
        thread_ts_iso=_ts_to_iso(ref.thread_ts),
        incremental=incremental,
        oldest=oldest,
        oldest_iso=_ts_to_iso(oldest),
    )

    new_messages: list[dict[str, Any]] = [
        msg
        async for msg in client.iter_thread_replies(
            channel=ref.channel,
            thread_ts=ref.thread_ts,
            oldest=oldest,
        )
    ]

    latest_reply = _latest_ts(new_messages)
    if latest_reply is None and state is not None:
        latest_reply = state.latest_reply

    with transaction(conn):
        # Record the thread row first so the messages FK constraint is satisfied.
        record_thread_refresh(conn, ref.channel, ref.thread_ts, latest_reply)
        written = upsert_messages(conn, ref.channel, ref.thread_ts, new_messages)

    total = count_messages(conn, ref.channel, ref.thread_ts)
    log.info(
        "fetch_thread_done",
        channel=ref.channel,
        thread_ts=ref.thread_ts,
        thread_ts_iso=_ts_to_iso(ref.thread_ts),
        written=written,
        total=total,
        incremental=incremental,
    )
    return FetchResult(
        channel=ref.channel,
        thread_ts=ref.thread_ts,
        fetched_messages=written,
        total_messages=total,
        incremental=incremental,
    )


def load_thread(conn: sqlite3.Connection, ref: ThreadRef) -> list[CachedMessage]:
    """Return the cached messages for a thread, ordered by ts."""
    return load_thread_messages(conn, ref.channel, ref.thread_ts)


async def fetch_channel_messages(
    conn: sqlite3.Connection,
    client: SlackClient,
    channel: str,
    full_threads: bool = False,
    oldest: str | None = None,
) -> ChannelFetchResult:
    """Fetch messages from a channel.

    By default only top-level messages are fetched via conversations.history
    (standalone messages and thread parents, but not thread replies).  When
    *full_threads* is True, every thread that has replies is also fetched in
    full via conversations.replies, concurrently.

    *oldest* limits the history scan to messages with ts >= oldest (epoch
    seconds as a string).  When None, the entire channel history is fetched.
    """
    log.info(
        "fetch_channel_messages_start",
        channel=channel,
        full_threads=full_threads,
        oldest=oldest,
        oldest_iso=_ts_to_iso(oldest),
    )

    history: list[dict[str, Any]] = [
        msg async for msg in client.iter_channel_history(channel=channel, oldest=oldest)
    ]
    log.info("fetch_channel_history_done", channel=channel, count=len(history))

    written = 0
    threads_with_replies_fetched = 0

    with transaction(conn):
        for msg in history:
            thread_ts = msg.get("thread_ts") or msg["ts"]
            record_thread_refresh(conn, channel, thread_ts, None)
            written += upsert_messages(conn, channel, thread_ts, [msg])

    if full_threads:
        parent_tss = sorted(
            {
                msg.get("thread_ts") or msg["ts"]
                for msg in history
                if msg.get("reply_count", 0) > 0 or msg.get("latest_reply")
            }
        )
        log.info("fetch_channel_threads_start", channel=channel, thread_count=len(parent_tss))

        async def fetch_thread_replies(thread_ts: str) -> list[dict[str, Any]]:
            return [
                msg
                async for msg in client.iter_thread_replies(channel=channel, thread_ts=thread_ts)
            ]

        results = await asyncio.gather(*(fetch_thread_replies(ts) for ts in parent_tss))
        for thread_ts, replies in zip(parent_tss, results, strict=True):
            if not replies:
                continue
            latest = _latest_ts(replies)
            with transaction(conn):
                record_thread_refresh(conn, channel, thread_ts, latest)
                written += upsert_messages(conn, channel, thread_ts, replies)
            threads_with_replies_fetched += 1

        log.info(
            "fetch_channel_threads_done",
            channel=channel,
            threads_fetched=threads_with_replies_fetched,
        )

    total = count_channel_messages(conn, channel)
    log.info(
        "fetch_channel_messages_done",
        channel=channel,
        written=written,
        total=total,
        threads_with_replies_fetched=threads_with_replies_fetched,
    )
    return ChannelFetchResult(
        channel=channel,
        fetched_messages=written,
        total_messages=total,
        threads_with_replies_fetched=threads_with_replies_fetched,
    )


async def fetch_search(
    conn: sqlite3.Connection,
    client: SlackClient,
    query: str,
    count: int = 20,
    sort: str = "timestamp",
    sort_dir: str = "desc",
    full_threads: bool = False,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> SearchFetchResult:
    """Search Slack via search.messages and cache every matched message.

    Each match carries its own ``channel`` and ``ts``; it is upserted into the
    messages table under its ``(channel, thread_ts)`` thread (defaulting the
    thread ts to the message ts when Slack omits one, matching the channel
    fetch behaviour).  When *full_threads* is True, every distinct matched
    thread is then fetched in full via conversations.replies.

    ``limit`` caps the total number of matches fetched; pass a non-positive
    value to fetch every page.

    Returns the raw matches so the caller can render them (with permalinks)
    without re-reading the cache.
    """
    log.info(
        "fetch_search_start",
        query=query,
        count=count,
        sort=sort,
        sort_dir=sort_dir,
        full_threads=full_threads,
        limit=limit,
    )

    matches: list[dict[str, Any]] = [
        match
        async for match in client.iter_search_messages(
            query=query, count=count, sort=sort, sort_dir=sort_dir, limit=limit
        )
    ]
    log.info("fetch_search_matches", query=query, matches=len(matches))

    # search.messages returns ``channel`` as an object (``{"id", "name", ...}``)
    # rather than the bare id used everywhere else, so normalise each match to a
    # string channel id in place. Callers (caching below and rendering) can then
    # treat ``channel`` uniformly.
    for msg in matches:
        msg["channel"] = _normalize_channel_id(msg.get("channel"))

    written = 0
    seen = 0
    threads_touched: set[tuple[str, str]] = set()
    threads_new: set[tuple[str, str]] = set()

    # In default mode the search match is the only source for the message, so
    # cache each one directly. In --full-threads mode we skip this step:
    # ``conversations.replies`` always returns the parent message too, and
    # Slack decorates ``search.messages`` text with query-highlighting
    # backticks that the replies endpoint does not. Caching both would
    # oscillate every run.
    if not full_threads:
        with transaction(conn):
            for msg in matches:
                channel = msg.get("channel")
                if not channel or not msg.get("ts"):
                    continue
                thread_ts = msg.get("thread_ts") or msg["ts"]
                record_thread_refresh(conn, channel, thread_ts, None)
                n = upsert_messages(conn, channel, thread_ts, [msg])
                seen += 1
                written += n
                threads_touched.add((channel, thread_ts))
                if n:
                    threads_new.add((channel, thread_ts))
    else:
        for msg in matches:
            channel = msg.get("channel")
            if not channel or not msg.get("ts"):
                continue
            thread_ts = msg.get("thread_ts") or msg["ts"]
            threads_touched.add((channel, thread_ts))

    if full_threads:
        log.info(
            "fetch_search_threads_start",
            query=query,
            thread_count=len(threads_touched),
        )

        async def fetch_one(channel: str, thread_ts: str) -> list[dict[str, Any]]:
            return [
                msg
                async for msg in client.iter_thread_replies(channel=channel, thread_ts=thread_ts)
            ]

        ordered = sorted(threads_touched)
        results = await asyncio.gather(*(fetch_one(c, t) for c, t in ordered))

        # Build a quick lookup so we can fall back to the search match for any
        # thread that ``conversations.replies`` returned nothing for (defensive
        # - in practice replies always includes at least the parent).
        match_by_thread: dict[tuple[str, str], dict[str, Any]] = {}
        for msg in matches:
            channel = msg.get("channel")
            if not channel or not msg.get("ts"):
                continue
            thread_ts = msg.get("thread_ts") or msg["ts"]
            match_by_thread.setdefault((channel, thread_ts), msg)

        for (channel, thread_ts), replies in zip(ordered, results, strict=True):
            latest = _latest_ts(replies) if replies else None
            with transaction(conn):
                record_thread_refresh(conn, channel, thread_ts, latest)
                if replies:
                    n = upsert_messages(conn, channel, thread_ts, replies)
                    seen += len(replies)
                else:
                    # Fallback: cache the search match directly.
                    fallback = match_by_thread.get((channel, thread_ts))
                    if fallback is None:
                        continue
                    n = upsert_messages(conn, channel, thread_ts, [fallback])
                    seen += 1
                written += n
                if n:
                    threads_new.add((channel, thread_ts))

    log.info(
        "fetch_search_done",
        query=query,
        matches=len(matches),
        threads_seen=len(threads_touched),
        threads_new=len(threads_new),
        messages_seen=seen,
        messages_new=written,
    )
    return SearchFetchResult(
        query=query,
        matches=matches,
        threads_seen=len(threads_touched),
        threads_new=len(threads_new),
        messages_seen=seen,
        messages_new=written,
    )


_LIST_FLUSH_SIZE = 500


async def _list_pages(client: SlackClient, kind: str) -> AsyncIterator[list[dict[str, Any]]]:
    """Yield list-endpoint items in pages.

    Prefers the client's page-level iterator so each page is committed as soon
    as it arrives. Clients that only expose item-level iteration (test doubles,
    simple wrappers) fall back to fixed-size chunks.
    """
    page_iter = getattr(client, f"iter_{kind}_pages", None)
    if page_iter is not None:
        async for page in page_iter():
            yield page
        return

    batch: list[dict[str, Any]] = []
    async for item in getattr(client, f"iter_{kind}")():
        batch.append(item)
        if len(batch) >= _LIST_FLUSH_SIZE:
            yield batch
            batch = []
    if batch:
        yield batch


async def _stream_upsert(
    conn: sqlite3.Connection,
    pages: AsyncIterator[list[dict[str, Any]]],
    upsert: Callable[[sqlite3.Connection, Iterable[dict[str, Any]]], int],
) -> int:
    """Upsert pages of items, committing once per page.

    Committing after each page means a failure mid-enumeration (rate limit,
    network error, interrupt) keeps every page fetched so far, and memory stays
    flat instead of buffering the whole workspace before the first write.
    """
    processed = 0
    async for page in pages:
        if not page:
            continue
        with transaction(conn):
            processed += upsert(conn, page)
    return processed


async def fetch_user(conn: sqlite3.Connection, client: SlackClient, user: str) -> CachedUser | None:
    """Fetch a single user's profile from Slack and cache it.

    Uses ``users.info`` rather than the full ``users.list`` enumeration, so
    retrieving one user is a single API call. Returns the cached user, or None
    when Slack returns no user payload.
    """
    log.info("fetch_user_start", user=user)
    info = await client.get_user_info(user)
    if not info:
        log.warning("fetch_user_empty", user=user)
        return None
    info.setdefault("id", user)
    with transaction(conn):
        upsert_users(conn, [info])
    log.info("fetch_user_done", user=info["id"])
    return get_user(conn, info["id"])


async def fetch_users(conn: sqlite3.Connection, client: SlackClient) -> ListFetchResult:
    """Fetch every workspace user from Slack and cache them."""
    log.info("fetch_users_start")
    before = count_users(conn)
    processed = await _stream_upsert(conn, _list_pages(client, "users"), upsert_users)

    total = count_users(conn)
    added = total - before
    log.info("fetch_users_done", processed=processed, added=added, total=total)
    return ListFetchResult(processed=processed, added=added, total=total)


async def fetch_channel(
    conn: sqlite3.Connection, client: SlackClient, channel: str
) -> CachedChannel | None:
    """Fetch a single channel's info from Slack and cache it.

    Uses ``conversations.info`` rather than the full ``conversations.list``
    enumeration, so retrieving one channel is a single API call. Returns the
    cached channel, or None when Slack returns no channel payload.
    """
    log.info("fetch_channel_start", channel=channel)
    info = await client.get_channel_info(channel)
    if not info:
        log.warning("fetch_channel_empty", channel=channel)
        return None
    info.setdefault("id", channel)
    with transaction(conn):
        upsert_channels(conn, [info])
    log.info("fetch_channel_done", channel=info["id"])
    return get_channel(conn, info["id"])


async def fetch_channels(conn: sqlite3.Connection, client: SlackClient) -> ListFetchResult:
    """Fetch every visible channel from Slack and cache them."""
    log.info("fetch_channels_start")
    before = count_channels(conn)
    processed = await _stream_upsert(conn, _list_pages(client, "channels"), upsert_channels)

    total = count_channels(conn)
    added = total - before
    log.info("fetch_channels_done", processed=processed, added=added, total=total)
    return ListFetchResult(processed=processed, added=added, total=total)
