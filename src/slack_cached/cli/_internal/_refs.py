"""Resolving the CLI's positional target and output format from flags."""

import sys
from dataclasses import dataclass

from slack_cached.cli._internal._channels import (
    _is_user_token,
    _resolve_channel,
    _resolve_dm_channel,
)
from slack_cached.cli._internal._shared import CommonArgs
from slack_cached.urls import parse_channel_ts, parse_channel_url, parse_thread_url


@dataclass(frozen=True)
class Target:
    """A resolved query target: a whole channel or one thread within it.

    ``thread_ts`` is None to read the channel, or a thread root ts to read a
    single thread inside ``channel``.
    """

    channel: str
    thread_ts: str | None = None


def _looks_like_url(token: str) -> bool:
    """Heuristic: does ``token`` name a Slack permalink rather than an entity?"""
    return token.startswith(("http://", "https://")) or ".slack.com" in token


def _parse_ts(channel: str, ts: str) -> str | None:
    """Validate and normalize a ``--ts`` value for ``channel``, else print an error."""
    try:
        return parse_channel_ts(channel, ts).thread_ts
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


async def _resolve_target(
    common: CommonArgs, raw: str | None, ts: str | None
) -> Target | None:
    """Resolve a positional target (URL, channel, or DM) to a query target.

    A permalink resolves to either its channel (channel URL) or its thread
    (thread URL). Any other token is treated as a channel id/name or, when it
    looks like a user, an ``@handle``/user id resolving to that DM. ``ts``
    selects a thread inside the resolved channel.
    """
    token = (raw or "").strip()
    if not token:
        raise SystemExit("Provide a URL, channel, or user to target.")

    if _looks_like_url(token):
        channel_url = parse_channel_url(token)
        if channel_url is not None:
            if ts is None:
                return Target(channel_url)
            thread_ts = _parse_ts(channel_url, ts)
            if thread_ts is None:
                return None
            return Target(channel_url, thread_ts)
        try:
            ref = parse_thread_url(token)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None
        return Target(ref.channel, ref.thread_ts)

    if _is_user_token(token):
        channel = await _resolve_dm_channel(common, token)
    else:
        channel = await _resolve_channel(common, token)
    if channel is None:
        return None

    if ts is None:
        return Target(channel)
    thread_ts = _parse_ts(channel, ts)
    if thread_ts is None:
        return None
    return Target(channel, thread_ts)


def _output_format(json_flag: bool, jsonl_flag: bool) -> str:
    """Resolve the requested output format, enforcing --json/--jsonl exclusion.

    Returns 'human', 'json', or 'jsonl'. Raises SystemExit if both flags are set.
    """
    if json_flag and jsonl_flag:
        print("--json and --jsonl are mutually exclusive.", file=sys.stderr)
        raise SystemExit(2)
    if jsonl_flag:
        return "jsonl"
    if json_flag:
        return "json"
    return "human"
