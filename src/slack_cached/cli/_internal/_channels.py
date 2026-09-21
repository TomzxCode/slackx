"""Channel and target resolution helpers (used by show, fetch, poll, search)."""

import sqlite3
import sys
from collections.abc import Iterable

from slack_cached.cli._internal._shared import CommonArgs
from slack_cached.storage import (
    find_im_channel_for_user,
    find_user_by_handle,
    load_channel_display_names,
    load_channels,
)


def _is_channel_id(token: str) -> bool:
    """Heuristic: decide whether a token is a channel id rather than a name.

    Slack channel names are always lowercase (letters, digits, hyphens,
    underscores), so any token containing an uppercase letter is treated as an
    id. A token with no cased letters at all (e.g. a numeric id) is also
    treated as an id. Everything else is treated as a name.
    """
    has_upper = any(c.isupper() for c in token)
    has_lower = any(c.islower() for c in token)
    return has_upper or not has_lower


def _channel_name_index(conn: sqlite3.Connection) -> dict[str, str]:
    """Return a {name: id} map of cached channels."""
    return {ch.name: ch.id for ch in load_channels(conn) if ch.name}


def _channel_id_names(conn: sqlite3.Connection, channel_ids: Iterable[str]) -> dict[str, str]:
    """Return a {channel_id: name} map for just the requested channels.

    Direct channels resolve to the display name of the peer user. Uses one
    lookup per channel rather than loading every cached channel, so cost
    scales with the matches rather than the whole workspace.
    """
    return load_channel_display_names(conn, channel_ids)


async def _resolve_channels(common: CommonArgs, entries: Iterable[str]) -> list[str] | None:
    """Resolve channel tokens (ids, bare names, or '#'-prefixed names) to ids.

    Names are resolved against the cached channels; when a name is missing
    from the cache the channels are fetched from Slack once and resolution is
    retried. Returns None and prints an error when a name cannot be resolved.
    """
    # Imported via module reference so monkeypatch on _client._build_client works.
    from slack_cached.cli._internal import _client

    entries = [e.strip().lstrip("#").strip() for e in entries]
    entries = [e for e in entries if e]

    resolved: list[str] = []
    names = [e for e in entries if not _is_channel_id(e)]
    for entry in entries:
        if _is_channel_id(entry):
            resolved.append(entry)

    if not names:
        return resolved

    from slack_cached.cache import fetch_channels

    # Resolve against the offline-resolved workspace database first; only hit
    # the network (and its auth.test-resolved workspace) when names are
    # missing from the cache.
    name_to_id: dict[str, str] = {}
    try:
        async with _client._open_db(common) as conn:
            name_to_id = _channel_name_index(conn)
    except SystemExit:
        name_to_id = {}

    if any(n not in name_to_id for n in names):
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            name_to_id = _channel_name_index(conn)
            if any(n not in name_to_id for n in names):
                await fetch_channels(conn, client)
            name_to_id = _channel_name_index(conn)

    unresolved: list[str] = []
    for name in names:
        channel_id = name_to_id.get(name)
        if channel_id is None:
            unresolved.append(name)
        else:
            resolved.append(channel_id)

    if unresolved:
        joined = ", ".join(unresolved)
        print(
            f"error: could not resolve channel name(s): {joined} "
            "(run 'slackx fetch-channels' or check the spelling)",
            file=sys.stderr,
        )
        return None
    return resolved


async def _resolve_poll_channels(common: CommonArgs, raw: str) -> list[str] | None:
    """Resolve a comma-separated --channels value to channel ids.

    Each entry may be a channel id (e.g. C0123456), a bare name (e.g. general),
    or a '#'-prefixed name (e.g. #general). Names are resolved against the
    cached channels. Returns None and prints an error when no entries are
    given or a name cannot be resolved.
    """
    entries = [e.strip() for e in raw.split(",")]
    entries = [e for e in entries if e]
    if not entries:
        print("error: --channels must contain at least one channel", file=sys.stderr)
        return None
    return await _resolve_channels(common, entries)


async def _resolve_channel(common: CommonArgs, token: str) -> str | None:
    """Resolve a single channel token (id, bare name, or '#'-prefixed name).

    Names are resolved against the cached channels; the cache is refreshed from
    Slack once if the name is missing. Returns None and prints an error when
    the name cannot be resolved.
    """
    resolved = await _resolve_channels(common, [token])
    if not resolved:
        return None
    return resolved[0]


def _is_user_token(token: str) -> bool:
    """Heuristic: decide whether a token names a user rather than a channel.

    An ``@``-prefixed handle always does. A token that looks like a Slack user
    id (``U``/``W`` prefix, no lowercase) is also treated as a user; channel
    names are lowercase, so this does not collide with them.
    """
    if token.startswith("@"):
        return True
    return token[:1] in ("U", "W") and _is_channel_id(token)


async def _resolve_dm_channel(common: CommonArgs, token: str) -> str | None:
    """Resolve an ``@handle`` or user id to the direct message channel id.

    The user and channel caches are consulted first, then refreshed from Slack
    once on a miss. Returns None and prints an error when the user or their DM
    channel cannot be resolved.
    """
    # Imported via module reference so monkeypatch on _client._build_client works.
    from slack_cached.cli._internal import _client

    handle = token[1:].strip() if token.startswith("@") else None
    if handle is not None and not handle:
        print("error: provide a handle after '@'.", file=sys.stderr)
        return None
    user_id = None if handle is not None else token

    channel: str | None = None
    try:
        async with _client._open_db(common) as conn:
            if handle is not None:
                user_id = find_user_by_handle(conn, handle)
            if user_id is not None:
                channel = find_im_channel_for_user(conn, user_id)
                if channel is not None:
                    return channel
    except SystemExit:
        pass

    from slack_cached.cache import fetch_channels, fetch_users

    async with (
        _client._open_client(common) as client,
        _client._open_db(common, client) as conn,
    ):
        if handle is not None and user_id is None:
            user_id = find_user_by_handle(conn, handle)
            if user_id is None:
                await fetch_users(conn, client)
                user_id = find_user_by_handle(conn, handle)
        if user_id is None:
            print(
                f"error: could not resolve user {token!r} "
                "(run 'slackx fetch-users' or check the spelling)",
                file=sys.stderr,
            )
            return None
        channel = find_im_channel_for_user(conn, user_id)
        if channel is None:
            await fetch_channels(conn, client)
            channel = find_im_channel_for_user(conn, user_id)

    if channel is None:
        print(f"error: no direct message channel found for {token!r}", file=sys.stderr)
        return None
    return channel
