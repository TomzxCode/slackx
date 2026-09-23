"""Output renderers for threads, channels, search results, users, and channels.

All renderers are pure functions that take already-loaded data and return a
string. They are independent of argument parsing and I/O. Human renderers
accept a keyword-only ``styled`` flag: when true, output carries ANSI styles
(bold, italics, dim, hyperlinks) and message text is rendered from Slack
mrkdwn; when false (the default), output is plain text with verbatim message
text, suitable for piping.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from slack_cached.cli._internal._blocks import _message_body_lines
from slack_cached.cli._internal._fields import SEARCH_DEFAULT_FIELDS
from slack_cached.cli._internal._format import _format_epoch, _format_ts
from slack_cached.cli._internal._style import _styler
from slack_cached.storage import (
    CachedChannel,
    CachedMessage,
    CachedUser,
    ChannelMessageEntry,
    DbStatus,
)
from slack_cached.urls import ThreadRef

# ---------------------------------------------------------------------------
# Thread renderers
# ---------------------------------------------------------------------------


def _render_human(
    ref: ThreadRef,
    messages: list[CachedMessage],
    user_names: dict[str, str] | None = None,
    *,
    styled: bool = False,
) -> str:
    """Render a thread as a human-readable string.

    When `user_names` maps a message's user id to a name, that name is shown
    instead of the raw id; unknown ids fall back to the id itself. With
    ``styled`` the header, timestamps, and authors carry ANSI styles and
    message text is rendered from Slack mrkdwn. Each message body renders its
    layout blocks and attachments when present (where bot messages keep their
    links), falling back to ``text`` otherwise.
    """
    names = user_names or {}
    s = _styler(styled)
    lines = [
        s.bold(f"Thread {ref.channel}/{ref.thread_ts}"),
        s.dim(f"{len(messages)} message(s)"),
        "",
    ]
    for msg in messages:
        author = names.get(msg.user, msg.user) if msg.user else "(unknown)"
        lines.append(f"{s.italic(f'[{_format_ts(msg.ts)}]')} {s.bold(author)}")
        for text_line in _message_body_lines(msg.text, msg.payload, s):
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
    messages: list[ChannelMessageEntry],
    user_names: dict[str, str] | None = None,
    channel_name: str | None = None,
    *,
    styled: bool = False,
) -> str:
    names = user_names or {}
    s = _styler(styled)
    header = channel_name or channel
    reply_count = sum(1 for msg in messages if msg.thread_ts != msg.ts)
    count_line = f"{len(messages)} message(s)"
    if reply_count:
        count_line += f" ({reply_count} thread replie(s))"
    lines = [
        s.bold(f"Channel {header}"),
        s.dim(count_line),
        "",
    ]
    for msg in messages:
        author = names.get(msg.user, msg.user) if msg.user else "(unknown)"
        if msg.thread_ts != msg.ts:
            lines.append(
                f"    {s.dim('\u21b3')} {s.italic(f'[{_format_ts(msg.ts)}]')} {s.bold(author)} "
                f"{s.dim(f'(thread {msg.thread_ts})')}"
            )
            indent = "        "
        else:
            lines.append(f"{s.italic(f'[{_format_ts(msg.ts)}]')} {s.bold(author)}")
            indent = "    "
        for text_line in _message_body_lines(msg.text, msg.payload, s):
            lines.append(f"{indent}{text_line}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _render_channel_json(
    channel: str,
    messages: list[ChannelMessageEntry],
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
        d = {
            "ts": msg.ts,
            "user": msg.user,
            "text": msg.text,
            "thread_ts": msg.thread_ts,
            "is_thread_reply": msg.thread_ts != msg.ts,
        }
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
    fields: Sequence[str] | None = None,
    *,
    styled: bool = False,
) -> str:
    """Render search matches as a human-readable string.

    Each match is printed with its channel, an optional permalink, the author
    and the message text, in the same style as `_render_human`. ``fields``
    restricts which parts are printed, mirroring the JSON renderer. With
    ``styled`` the header, channel labels, timestamps, and authors carry ANSI
    styles and permalinks become OSC 8 hyperlinks.
    """
    selected = set(fields or SEARCH_DEFAULT_FIELDS)
    names = user_names or {}
    ch_names = channel_names or {}
    s = _styler(styled)
    lines = [s.bold(f"Search: {query}"), s.dim(f"{len(matches)} match(es)"), ""]
    for msg in matches:
        channel = msg.get("channel") or "?"
        ch_label = ch_names.get(channel, channel)
        ts = msg.get("ts", "?")
        user = msg.get("user")
        author = names.get(user, user) if user else "(unknown)"
        text = msg.get("text") if msg.get("text") is not None else ""
        permalink = msg.get("permalink")
        if {"channel", "channel_name"} & selected:
            header = s.bold(f"[{ch_label}]")
            if permalink and "permalink" in selected:
                header = f"{header} {s.link(s.dim(permalink), permalink)}"
            lines.append(header)
        meta: list[str] = []
        if "ts" in selected:
            meta.append(s.italic(_format_ts(ts)))
        if {"user", "user_name"} & selected:
            meta.append(s.bold(author))
        if meta:
            lines.append(f"[{' '.join(meta)}]")
        if "text" in selected:
            text = s.mrkdwn(text) if text else text
            for text_line in text.splitlines() or [""]:
                lines.append(f"    {text_line}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _search_field_value(
    msg: dict[str, Any], field: str, names: dict[str, str], ch_names: dict[str, str]
) -> Any:
    """Return the value of a single search field for JSON output."""
    channel = msg.get("channel")
    user = msg.get("user")
    if field == "channel":
        return channel
    if field == "channel_name":
        return ch_names.get(channel) if channel else None
    if field == "ts":
        return msg.get("ts")
    if field == "thread_ts":
        return msg.get("thread_ts")
    if field == "user":
        return user
    if field == "user_name":
        return names.get(user) if user else None
    if field == "text":
        return msg.get("text")
    if field == "permalink":
        return msg.get("permalink")
    if field == "payload":
        return msg
    return None


def _render_search_json(
    query: str,
    matches: list[dict[str, Any]],
    user_names: dict[str, str] | None = None,
    channel_names: dict[str, str] | None = None,
    fields: Sequence[str] | None = None,
    *,
    indent: int | None = 2,
) -> str:
    """Render search matches as a JSON string (pretty-printed by default).

    ``fields`` selects and orders the keys emitted for each match; it defaults
    to every field except ``payload``. Pass ``indent=None`` to emit the whole
    payload as a single line.
    """
    selected = list(fields or SEARCH_DEFAULT_FIELDS)
    names = user_names or {}
    ch_names = channel_names or {}
    enriched: list[dict[str, Any]] = [
        {field: _search_field_value(msg, field, names, ch_names) for field in selected}
        for msg in matches
    ]
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
    *,
    styled: bool = False,
) -> str:
    selected = fields or ("id", "name", "real_name")
    s = _styler(styled)
    lines = [s.bold(f"{len(users)} user(s)"), ""]
    for user in users:
        values = [_user_field_human(user, field, s) for field in selected]
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


def _user_field_human(user: CachedUser, field: str, s: Any = None) -> str:
    if field == "id":
        return user.id
    if field == "name":
        value = user.name or "(no name)"
        return s.bold(value) if s else value
    if field == "real_name":
        value = user.real_name or ""
        return s.bold(value) if s and value else value
    if field == "fetched_at":
        value = _format_epoch(user.fetched_at)
        return s.italic(value) if s else value
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
    *,
    styled: bool = False,
) -> str:
    names = display_names or {}
    selected = fields or ("id", "name", "is_private")
    s = _styler(styled)
    lines = [s.bold(f"{len(channels)} channel(s)"), ""]
    for channel in channels:
        values = [_channel_field_human(channel, field, names, s) for field in selected]
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


def _channel_field_human(
    channel: CachedChannel, field: str, names: dict[str, str], s: Any = None
) -> str:
    if field == "id":
        return channel.id
    if field in ("name", "display_name"):
        value = names.get(channel.id) or channel.name or "(no name)"
        return s.bold(value) if s else value
    if field == "is_private":
        if channel.payload.get("is_im"):
            visibility = "direct"
        else:
            visibility = "private" if channel.is_private else "public"
        value = f"({visibility})"
        return s.dim(value) if s else value
    if field == "fetched_at":
        value = _format_epoch(channel.fetched_at)
        return s.italic(value) if s else value
    if field == "payload":
        return json.dumps(channel.payload, ensure_ascii=False, sort_keys=True)
    return ""


def _channel_field_json(channel: CachedChannel, field: str, names: dict[str, str]) -> Any:
    if field == "display_name":
        return names.get(channel.id) or channel.name
    if field == "payload":
        return channel.payload
    return getattr(channel, field)


def _render_status_human(status: DbStatus, *, styled: bool = False) -> str:
    s = _styler(styled)

    def line(label: str, count: int, updated_at: float | None) -> str:
        return (
            f"{s.bold(str(count))} {label}(s)  "
            f"{s.dim('last updated')} {s.italic(_format_epoch(updated_at))}"
        )

    lines = [
        line("channel", status.channel_count, status.channels_updated_at),
        line("user", status.user_count, status.users_updated_at),
        line("thread", status.thread_count, status.threads_updated_at),
        f"{s.bold(str(status.message_count))} message(s)",
    ]
    return "\n".join(lines) + "\n"
