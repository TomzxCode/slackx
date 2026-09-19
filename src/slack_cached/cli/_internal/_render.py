"""Output renderers for threads, channels, search results, users, and channels.

All renderers are pure functions that take already-loaded data and return a
string. They are independent of argument parsing and I/O.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from slack_cached.cli._internal._format import _format_epoch, _format_ts
from slack_cached.storage import CachedChannel, CachedMessage, CachedUser, DbStatus
from slack_cached.urls import ThreadRef

# ---------------------------------------------------------------------------
# Thread renderers
# ---------------------------------------------------------------------------


def _render_human(
    ref: ThreadRef,
    messages: list[CachedMessage],
    user_names: dict[str, str] | None = None,
) -> str:
    """Render a thread as a human-readable string.

    When `user_names` maps a message's user id to a name, that name is shown
    instead of the raw id; unknown ids fall back to the id itself.
    """
    names = user_names or {}
    lines = [
        f"Thread {ref.channel}/{ref.thread_ts}",
        f"{len(messages)} message(s)",
        "",
    ]
    for msg in messages:
        author = names.get(msg.user, msg.user) if msg.user else "(unknown)"
        text = msg.text if msg.text is not None else ""
        lines.append(f"[{_format_ts(msg.ts)}] {author}")
        for text_line in text.splitlines() or [""]:
            lines.append(f"    {text_line}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _render_json(
    ref: ThreadRef,
    messages: list[CachedMessage],
    user_names: dict[str, str] | None = None,
    channel_name: str | None = None,
    *,
    indent: int | None = 2,
) -> str:
    """Render a thread as a JSON string (pretty-printed by default).

    Pass ``indent=None`` to emit the whole payload as a single line, suitable
    for JSONL output (one record per invocation).
    """
    names = user_names or {}
    enriched: list[dict[str, Any]] = []
    for msg in messages:
        d = asdict(msg)
        if msg.user and msg.user in names:
            d["user_name"] = names[msg.user]
        enriched.append(d)
    payload: dict[str, Any] = {
        "channel": ref.channel,
        "channel_name": channel_name,
        "thread_ts": ref.thread_ts,
        "message_count": len(messages),
        "messages": enriched,
    }
    return json.dumps(payload, ensure_ascii=False, indent=indent) + "\n"


# ---------------------------------------------------------------------------
# Channel message renderers
# ---------------------------------------------------------------------------


def _render_channel_human(
    channel: str,
    messages: list[CachedMessage],
    user_names: dict[str, str] | None = None,
    channel_name: str | None = None,
) -> str:
    names = user_names or {}
    header = channel_name or channel
    lines = [
        f"Channel {header}",
        f"{len(messages)} message(s)",
        "",
    ]
    for msg in messages:
        author = names.get(msg.user, msg.user) if msg.user else "(unknown)"
        text = msg.text if msg.text is not None else ""
        lines.append(f"[{_format_ts(msg.ts)}] {author}")
        for text_line in text.splitlines() or [""]:
            lines.append(f"    {text_line}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _render_channel_json(
    channel: str,
    messages: list[CachedMessage],
    user_names: dict[str, str] | None = None,
    channel_name: str | None = None,
    *,
    indent: int | None = 2,
) -> str:
    """Render a channel's messages as JSON (pretty-printed by default).

    Pass ``indent=None`` to emit the whole payload as a single line.
    """
    names = user_names or {}
    enriched: list[dict[str, Any]] = []
    for msg in messages:
        d = {"ts": msg.ts, "user": msg.user, "text": msg.text}
        if msg.user and msg.user in names:
            d["user_name"] = names[msg.user]
        enriched.append(d)
    payload: dict[str, Any] = {
        "channel": channel,
        "channel_name": channel_name,
        "message_count": len(messages),
        "messages": enriched,
    }
    return json.dumps(payload, ensure_ascii=False, indent=indent) + "\n"


# ---------------------------------------------------------------------------
# Search renderers
# ---------------------------------------------------------------------------


def _render_search_human(
    query: str,
    matches: list[dict[str, Any]],
    user_names: dict[str, str] | None = None,
    channel_names: dict[str, str] | None = None,
) -> str:
    """Render search matches as a human-readable string.

    Each match is printed with its channel, an optional permalink, the author
    and the message text, in the same style as `_render_human`.
    """
    names = user_names or {}
    ch_names = channel_names or {}
    lines = [f"Search: {query}", f"{len(matches)} match(es)", ""]
    for msg in matches:
        channel = msg.get("channel") or "?"
        ch_label = ch_names.get(channel, channel)
        ts = msg.get("ts", "?")
        user = msg.get("user")
        author = names.get(user, user) if user else "(unknown)"
        text = msg.get("text") if msg.get("text") is not None else ""
        permalink = msg.get("permalink")
        header = f"[{ch_label}]"
        if permalink:
            header = f"{header} {permalink}"
        lines.append(header)
        lines.append(f"[{_format_ts(ts)}] {author}")
        for text_line in text.splitlines() or [""]:
            lines.append(f"    {text_line}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _render_search_json(
    query: str,
    matches: list[dict[str, Any]],
    user_names: dict[str, str] | None = None,
    channel_names: dict[str, str] | None = None,
    *,
    indent: int | None = 2,
) -> str:
    """Render search matches as a JSON string (pretty-printed by default).

    Pass ``indent=None`` to emit the whole payload as a single line.
    """
    names = user_names or {}
    ch_names = channel_names or {}
    enriched: list[dict[str, Any]] = []
    for msg in matches:
        channel = msg.get("channel")
        user = msg.get("user")
        entry: dict[str, Any] = {
            "channel": channel,
            "channel_name": ch_names.get(channel) if channel else None,
            "ts": msg.get("ts"),
            "thread_ts": msg.get("thread_ts"),
            "user": user,
            "text": msg.get("text"),
            "permalink": msg.get("permalink"),
        }
        if user and user in names:
            entry["user_name"] = names[user]
        enriched.append(entry)
    payload: dict[str, Any] = {
        "query": query,
        "match_count": len(matches),
        "matches": enriched,
    }
    return json.dumps(payload, ensure_ascii=False, indent=indent) + "\n"


# ---------------------------------------------------------------------------
# Listing renderers (users, channels)
# ---------------------------------------------------------------------------


def _render_users_human(
    users: list[CachedUser],
    fields: Sequence[str] | None = None,
) -> str:
    selected = fields or ("id", "name", "real_name")
    lines = [f"{len(users)} user(s)", ""]
    for user in users:
        values = [_user_field_human(user, field) for field in selected]
        lines.append("  ".join(value for value in values if value))
    return "\n".join(lines).rstrip("\n") + "\n"


def _render_users_json(
    users: list[CachedUser],
    fields: Sequence[str] | None = None,
    *,
    indent: int | None = 2,
) -> str:
    selected = list(fields or ("id", "name", "real_name"))
    payload = {
        "user_count": len(users),
        "users": [{field: _user_field_json(user, field) for field in selected} for user in users],
    }
    return json.dumps(payload, ensure_ascii=False, indent=indent) + "\n"


def _user_field_human(user: CachedUser, field: str) -> str:
    if field == "id":
        return user.id
    if field == "name":
        return user.name or "(no name)"
    if field == "real_name":
        return user.real_name or ""
    if field == "fetched_at":
        return _format_epoch(user.fetched_at)
    if field == "payload":
        return json.dumps(user.payload, ensure_ascii=False, sort_keys=True)
    return ""


def _user_field_json(user: CachedUser, field: str) -> Any:
    if field == "payload":
        return user.payload
    return getattr(user, field)


def _render_channels_human(
    channels: list[CachedChannel],
    display_names: dict[str, str] | None = None,
    fields: Sequence[str] | None = None,
) -> str:
    names = display_names or {}
    selected = fields or ("id", "name", "is_private")
    lines = [f"{len(channels)} channel(s)", ""]
    for channel in channels:
        values = [_channel_field_human(channel, field, names) for field in selected]
        lines.append("  ".join(value for value in values if value))
    return "\n".join(lines).rstrip("\n") + "\n"


def _render_channels_json(
    channels: list[CachedChannel],
    display_names: dict[str, str] | None = None,
    fields: Sequence[str] | None = None,
    *,
    indent: int | None = 2,
) -> str:
    names = display_names or {}
    selected = list(fields or ("id", "name", "is_private"))
    payload = {
        "channel_count": len(channels),
        "channels": [
            {field: _channel_field_json(channel, field, names) for field in selected}
            for channel in channels
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=indent) + "\n"


def _channel_field_human(channel: CachedChannel, field: str, names: dict[str, str]) -> str:
    if field == "id":
        return channel.id
    if field in ("name", "display_name"):
        return names.get(channel.id) or channel.name or "(no name)"
    if field == "is_private":
        if channel.payload.get("is_im"):
            visibility = "direct"
        else:
            visibility = "private" if channel.is_private else "public"
        return f"({visibility})"
    if field == "fetched_at":
        return _format_epoch(channel.fetched_at)
    if field == "payload":
        return json.dumps(channel.payload, ensure_ascii=False, sort_keys=True)
    return ""


def _channel_field_json(channel: CachedChannel, field: str, names: dict[str, str]) -> Any:
    if field == "display_name":
        return names.get(channel.id) or channel.name
    if field == "payload":
        return channel.payload
    return getattr(channel, field)


def _render_status_human(status: DbStatus) -> str:
    def line(label: str, count: int, updated_at: float | None) -> str:
        return f"{count} {label}(s)  last updated {_format_epoch(updated_at)}"

    lines = [
        line("channel", status.channel_count, status.channels_updated_at),
        line("user", status.user_count, status.users_updated_at),
        line("thread", status.thread_count, status.threads_updated_at),
        f"{status.message_count} message(s)",
    ]
    return "\n".join(lines) + "\n"
