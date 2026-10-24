"""JSON-RPC methods mirroring the slackx CLI commands.

Every method takes a :class:`RpcContext` (the server's bound database and Slack
API settings) plus a JSON object of parameters, and returns a JSON-serializable
result. The shapes match what the CLI prints with ``--json`` where a command
has a JSON form, so a client can switch between the two surfaces.

Method handlers reuse the same CLI helpers and cache orchestration functions as
the commands themselves. They never write command output; failures are raised as
:class:`RpcError` so the transport can turn them into JSON-RPC error objects.
"""

from __future__ import annotations

import asyncio
import sqlite3
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from slackx._log import get_logger
from slackx.cli._internal._client import _open_client, _open_db, _open_db_at
from slackx.cli._internal._duration import _oldest_ts_from_last
from slackx.cli._internal._fields import (
    CHANNEL_DEFAULT_FIELDS,
    CHANNEL_FIELDS,
    SEARCH_DEFAULT_FIELDS,
    SEARCH_FIELDS,
    USER_DEFAULT_FIELDS,
    USER_FIELDS,
    parse_fields,
)
from slackx.cli._internal._format import _build_user_names
from slackx.cli._internal._refs import Target, _resolve_target
from slackx.cli._internal._render import (
    _channel_payload,
    _channels_payload,
    _search_payload,
    _thread_payload,
    _users_payload,
)
from slackx.cli._internal._shared import CommonArgs
from slackx.defaults import DEFAULT_SEARCH_LIMIT
from slackx.rpc.protocol import (
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    SERVER_ERROR,
    RpcError,
)

log = get_logger(__name__)


@dataclass(frozen=True)
class RpcContext:
    """Server-owned state every RPC method operates against.

    ``db_path`` and ``api_base_url`` are fixed when the server starts, so a
    client cannot point a call at another workspace or Slack instance.
    """

    db_path: Path
    api_base_url: str | None = None
    log_level: str = "info"
    allow_exec: bool = True
    executable: str | None = None
    base_args: tuple[str, ...] = ()
    started_at: float = field(default_factory=time.time)

    @property
    def common(self) -> CommonArgs:
        """Return the CLI argument carrier pointing at this server's database."""
        return CommonArgs(
            db=self.db_path,
            api_base_url=self.api_base_url,
            log_level=self.log_level,
        )


Handler = Callable[[RpcContext, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class Method:
    """A registered JSON-RPC method and its documentation."""

    name: str
    description: str
    params: tuple[str, ...]
    handler: Handler


_METHODS: dict[str, Method] = {}


def method(name: str, description: str, params: Sequence[str] = ()) -> Callable[[Handler], Handler]:
    """Register a handler under ``name``."""

    def register(handler: Handler) -> Handler:
        _METHODS[name] = Method(name, description, tuple(params), handler)
        return handler

    return register


def list_methods(allow_exec: bool = True) -> list[dict[str, Any]]:
    """Return the method catalog, sorted by name."""
    entries = _METHODS.values()
    if not allow_exec:
        entries = [entry for entry in entries if entry.name != "cli.run"]
    return [
        {
            "name": entry.name,
            "description": entry.description,
            "params": list(entry.params),
        }
        for entry in sorted(entries, key=lambda item: item.name)
    ]


def server_version() -> str:
    """Return the installed slackx version, or a fallback for source checkouts."""
    try:
        return version("slackx")
    except PackageNotFoundError:
        return "0.1.0"


async def dispatch(ctx: RpcContext, name: str, params: dict[str, Any]) -> Any:
    """Run one method, converting application failures into JSON-RPC errors."""
    if name == "cli.run" and not ctx.allow_exec:
        raise RpcError(METHOD_NOT_FOUND, f"Method not found: {name}")
    entry = _METHODS.get(name)
    if entry is None:
        raise RpcError(METHOD_NOT_FOUND, f"Method not found: {name}")

    try:
        return await entry.handler(ctx, params)
    except RpcError:
        raise
    except SystemExit as exc:
        # CLI helpers signal fatal conditions (missing credentials, unknown
        # workspace) with SystemExit; carry their message to the caller.
        message = str(exc) or "command aborted"
        raise RpcError(SERVER_ERROR, message) from exc
    except Exception as exc:  # noqa: BLE001 - the transport must not leak a traceback
        log.exception("rpc_method_failed", method=name)
        raise RpcError(SERVER_ERROR, f"{type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


def _check_params(params: dict[str, Any], allowed: Sequence[str]) -> None:
    """Reject unknown parameters so typos do not silently do nothing."""
    unknown = sorted(set(params) - set(allowed))
    if unknown:
        raise RpcError(
            INVALID_PARAMS,
            f"unknown parameter(s): {', '.join(unknown)}",
            {"allowed": list(allowed)},
        )


def _str_param(
    params: dict[str, Any],
    name: str,
    *,
    required: bool = False,
    default: str | None = None,
    allow_empty: bool = False,
    nullable: bool = False,
) -> str | None:
    if name not in params:
        if required:
            raise RpcError(INVALID_PARAMS, f"missing required parameter: {name}")
        return default
    value = params[name]
    if value is None:
        if nullable:
            return None
        if required:
            raise RpcError(INVALID_PARAMS, f"missing required parameter: {name}")
        return default
    if not isinstance(value, str):
        raise RpcError(INVALID_PARAMS, f"parameter {name} must be a string")
    if not allow_empty and not value.strip():
        raise RpcError(INVALID_PARAMS, f"parameter {name} must not be empty")
    return value


def _bool_param(
    params: dict[str, Any],
    name: str,
    default: bool | None = None,
    *,
    nullable: bool = False,
) -> bool | None:
    if name not in params:
        return default
    value = params[name]
    if value is None and nullable:
        return None
    if not isinstance(value, bool):
        raise RpcError(INVALID_PARAMS, f"parameter {name} must be a boolean")
    return value


def _int_param(params: dict[str, Any], name: str, default: int) -> int:
    value = params.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RpcError(INVALID_PARAMS, f"parameter {name} must be an integer")
    return value


def _choice_param(params: dict[str, Any], name: str, default: str, choices: Sequence[str]) -> str:
    value = params.get(name, default)
    if value not in choices:
        raise RpcError(
            INVALID_PARAMS,
            f"parameter {name} must be one of: {', '.join(choices)}",
        )
    return value


def _fields_param(
    params: dict[str, Any],
    allowed: Sequence[str],
    default: Sequence[str],
) -> list[str]:
    raw = params.get("fields")
    if raw is None:
        return list(default)
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        raw = ",".join(raw)
    if not isinstance(raw, str):
        raise RpcError(INVALID_PARAMS, "parameter fields must be a string or a list of strings")
    try:
        return parse_fields(raw, allowed, default)
    except ValueError as exc:
        raise RpcError(INVALID_PARAMS, str(exc)) from exc


def _target_param(params: dict[str, Any]) -> str:
    target = _str_param(params, "target", required=True)
    assert target is not None
    return target


def _last_param(params: dict[str, Any]) -> str:
    return _str_param(params, "last", default="1d") or "1d"


def _oldest_for(last: str) -> str | None:
    try:
        return _oldest_ts_from_last(last)
    except ValueError as exc:
        raise RpcError(INVALID_PARAMS, str(exc)) from exc


async def _resolve_target_or_error(ctx: RpcContext, target: str, ts: str | None) -> Target:
    resolved = await _resolve_target(ctx.common, target, ts)
    if resolved is None:
        raise RpcError(SERVER_ERROR, f"could not resolve target {target!r}")
    return resolved


async def _resolve_channel_or_error(ctx: RpcContext, token: str) -> str:
    from slackx.cli._internal._channels import _resolve_channel

    resolved = await _resolve_channel(ctx.common, token)
    if resolved is None:
        raise RpcError(SERVER_ERROR, f"could not resolve channel {token!r}")
    return resolved


# ---------------------------------------------------------------------------
# Shared loading helpers (the same reads the CLI commands perform)
# ---------------------------------------------------------------------------


def _load_thread_view(
    conn: sqlite3.Connection, channel: str, thread_ts: str
) -> tuple[list[Any], dict[str, str], str | None]:
    from slackx.storage import load_channel_display_names, load_thread_messages

    messages = load_thread_messages(conn, channel, thread_ts)
    return (
        messages,
        _build_user_names(conn, messages),
        load_channel_display_names(conn, [channel]).get(channel),
    )


def _load_channel_view(
    conn: sqlite3.Connection,
    channel: str,
    with_thread_message: bool,
    oldest: str | None = None,
) -> tuple[list[Any], dict[str, str], str | None]:
    from slackx.storage import load_channel_display_names, load_channel_messages

    messages = load_channel_messages(
        conn, channel, oldest=oldest, include_thread_replies=with_thread_message
    )
    return (
        messages,
        _build_user_names(conn, messages),
        load_channel_display_names(conn, [channel]).get(channel),
    )


async def _fetch_thread_view(ctx: RpcContext, channel: str, thread_ts: str) -> None:
    from slackx.cache import fetch_thread
    from slackx.urls import ThreadRef

    async with _open_client(ctx.common) as client, _open_db(ctx.common, client) as conn:
        await fetch_thread(conn, client, ThreadRef(channel, thread_ts))


async def _fetch_channel_view(
    ctx: RpcContext, channel: str, *, full_threads: bool = False, oldest: str | None = None
) -> None:
    from slackx.cache import fetch_channel_messages

    async with _open_client(ctx.common) as client, _open_db(ctx.common, client) as conn:
        await fetch_channel_messages(
            conn, client, channel, full_threads=full_threads, oldest=oldest
        )


async def _mark_read(
    ctx: RpcContext, channel: str, thread_ts: str | None, reader: str | None
) -> None:
    """Advance ``reader``'s pointer to the newest cached message (CLI parity)."""
    from slackx.storage import latest_message_ts, set_last_read, transaction

    if reader is None:
        return
    reader = reader.strip()
    if not reader:
        return
    async with _open_db(ctx.common) as conn:
        marker_ts = latest_message_ts(conn, channel, thread_ts)
        if marker_ts is None:
            return
        with transaction(conn):
            set_last_read(conn, reader, channel, marker_ts, thread_ts)


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


@method("rpc.discover", "List the JSON-RPC methods this server exposes.")
async def _rpc_discover(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ())
    return {
        "name": "slackx",
        "version": server_version(),
        "methods": list_methods(ctx.allow_exec),
    }


@method("system.methods", "List the JSON-RPC methods this server exposes.")
async def _system_methods(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    """Alias kept for clients written against the first revision."""
    _check_params(params, ())
    return {"methods": list_methods(ctx.allow_exec)}


@method("server.info", "Report the server version, database, and method count.")
async def _server_info(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ())
    from slackx.workspace import workspace_name_from_db_path

    return {
        "name": "slackx",
        "version": server_version(),
        "workspace": workspace_name_from_db_path(ctx.db_path),
        "dbPath": str(ctx.db_path),
        "apiBaseUrl": ctx.api_base_url or "",
        "execEnabled": ctx.allow_exec,
        "methods": len(list_methods(ctx.allow_exec)),
        "startedAt": datetime.fromtimestamp(ctx.started_at, UTC).isoformat(),
    }


@method(
    "cli.run",
    "Run a slackx CLI command on the server and return its output and exit code.",
    ("args", "stdin"),
)
async def _cli_run(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    """Execute one CLI invocation in a child process.

    The server's database and API settings are appended as trailing flags, so
    the child reads and writes the same cache as the process holding it.
    """
    _check_params(params, ("args", "stdin"))
    args = params.get("args")
    if not isinstance(args, list) or not args or not all(isinstance(item, str) for item in args):
        raise RpcError(INVALID_PARAMS, "args must be a non-empty array of strings")
    stdin = params.get("stdin", "")
    if stdin is None:
        stdin = ""
    if not isinstance(stdin, str):
        raise RpcError(INVALID_PARAMS, "stdin must be a string")

    # RPC subcommands do not accept the cache flags, so leave them untouched.
    base_args = () if args[0] == "rpc" else ctx.base_args
    command = [ctx.executable or sys.executable, "-m", "slackx", *args, *base_args]
    process = await asyncio.to_thread(
        subprocess.run,
        command,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "stdout": process.stdout,
        "stderr": process.stderr,
        "exitCode": process.returncode,
    }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@method("cache.status", "Report cache counts and last-update times.")
async def _cache_status(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ())
    from slackx.storage import db_status
    from slackx.workspace import workspace_name_from_db_path

    with _open_db_at(ctx.db_path) as conn:
        snapshot = db_status(conn)
    return {
        "workspace": workspace_name_from_db_path(ctx.db_path),
        "db_path": str(ctx.db_path),
        **asdict(snapshot),
    }


@method(
    "cache.clear",
    "Delete cached data (all, messages, channels, users, or read markers).",
    ("target",),
)
async def _cache_clear(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("target",))
    target = _choice_param(
        params, "target", "all", ("all", "messages", "channels", "users", "read")
    )
    from slackx.storage import clear_cache

    with _open_db_at(ctx.db_path) as conn:
        cleared = clear_cache(
            conn,
            messages=target in ("all", "messages"),
            channels=target in ("all", "channels"),
            users=target in ("all", "users"),
            read_markers=target in ("all", "read"),
        )
    return asdict(cleared)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@method(
    "users.list",
    "List cached users, fetching them once when the cache is empty.",
    ("limit", "fields", "fetch"),
)
async def _users_list(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("limit", "fields", "fetch"))
    from slackx.storage import load_users

    limit = _int_param(params, "limit", 0)
    fetch = bool(_bool_param(params, "fetch", True))
    selected = _fields_param(params, USER_FIELDS, USER_DEFAULT_FIELDS)
    include_payload = "payload" in selected

    async with _open_db(ctx.common) as conn:
        users = load_users(conn, limit=limit, include_payload=include_payload)

    if not users and fetch:
        from slackx.cache import fetch_users

        async with _open_client(ctx.common) as client, _open_db(ctx.common, client) as conn:
            if not load_users(conn, limit=1):
                await fetch_users(conn, client)
            users = load_users(conn, limit=limit, include_payload=include_payload)

    return _users_payload(users, selected)


@method(
    "users.get",
    "Get one cached user, fetching it from Slack when missing.",
    ("user", "fields", "fetch"),
)
async def _users_get(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("user", "fields", "fetch"))
    from slackx.cache import fetch_user
    from slackx.storage import get_user

    user_id = _str_param(params, "user", required=True)
    assert user_id is not None
    fetch = bool(_bool_param(params, "fetch", True))
    selected = _fields_param(params, USER_FIELDS, USER_DEFAULT_FIELDS)

    async with _open_db(ctx.common) as conn:
        cached = get_user(conn, user_id)
    if cached is None and fetch:
        async with _open_client(ctx.common) as client, _open_db(ctx.common, client) as conn:
            cached = await fetch_user(conn, client, user_id)
    if cached is None:
        raise RpcError(SERVER_ERROR, f"user {user_id} is not cached")
    return _users_payload([cached], selected)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


@method(
    "channels.list",
    "List cached channels, fetching them once when the cache is empty.",
    ("limit", "fields", "fetch"),
)
async def _channels_list(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("limit", "fields", "fetch"))
    from slackx.storage import load_channel_display_names, load_channels

    limit = _int_param(params, "limit", 0)
    fetch = bool(_bool_param(params, "fetch", True))
    selected = _fields_param(params, CHANNEL_FIELDS, CHANNEL_DEFAULT_FIELDS)
    include_payload = bool({"is_private", "payload"} & set(selected))

    async with _open_db(ctx.common) as conn:
        channels = load_channels(conn, limit=limit, include_payload=include_payload)

    if not channels and fetch:
        from slackx.cache import fetch_channels

        async with _open_client(ctx.common) as client, _open_db(ctx.common, client) as conn:
            if not load_channels(conn, limit=1):
                await fetch_channels(conn, client)
            channels = load_channels(conn, limit=limit, include_payload=include_payload)

    display_names: dict[str, str] = {}
    if {"name", "display_name"} & set(selected):
        async with _open_db(ctx.common) as conn:
            display_names = load_channel_display_names(conn, [c.id for c in channels])
    return _channels_payload(channels, display_names, selected)


@method(
    "channels.get",
    "Get one cached channel, fetching it from Slack when missing.",
    ("channel", "fields", "fetch"),
)
async def _channels_get(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("channel", "fields", "fetch"))
    from slackx.cache import fetch_channel
    from slackx.storage import get_channel, load_channel_display_names

    channel = _str_param(params, "channel", required=True)
    assert channel is not None
    fetch = bool(_bool_param(params, "fetch", True))
    selected = _fields_param(params, CHANNEL_FIELDS, CHANNEL_DEFAULT_FIELDS)

    resolved = await _resolve_channel_or_error(ctx, channel)
    async with _open_db(ctx.common) as conn:
        cached = get_channel(conn, resolved)
    if cached is None and fetch:
        async with _open_client(ctx.common) as client, _open_db(ctx.common, client) as conn:
            cached = await fetch_channel(conn, client, resolved)
    if cached is None:
        raise RpcError(SERVER_ERROR, f"channel {resolved} is not cached")

    display_names: dict[str, str] = {}
    if {"name", "display_name"} & set(selected):
        async with _open_db(ctx.common) as conn:
            display_names = load_channel_display_names(conn, [resolved])
    return _channels_payload([cached], display_names, selected)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


@method(
    "conversations.fetch",
    "Cache or refresh a thread, or fetch a channel's messages.",
    ("target", "ts", "full_threads", "last"),
)
async def _conversations_fetch(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("target", "ts", "full_threads", "last"))
    from slackx.cache import fetch_channel_messages, fetch_thread
    from slackx.urls import ThreadRef

    target = _target_param(params)
    ts = _str_param(params, "ts")
    full_threads = bool(_bool_param(params, "full_threads", False))
    last = _last_param(params)
    resolved = await _resolve_target_or_error(ctx, target, ts)

    if resolved.thread_ts is None:
        oldest = _oldest_for(last)
        async with _open_client(ctx.common) as client, _open_db(ctx.common, client) as conn:
            result = await fetch_channel_messages(
                conn, client, resolved.channel, full_threads=full_threads, oldest=oldest
            )
        return {"kind": "channel", **asdict(result)}

    async with _open_client(ctx.common) as client, _open_db(ctx.common, client) as conn:
        result = await fetch_thread(conn, client, ThreadRef(resolved.channel, resolved.thread_ts))
    return {"kind": "thread", **asdict(result)}


@method(
    "conversations.get",
    "Get a cached thread or channel, fetching it first when missing.",
    ("target", "ts", "fetch", "with_thread_message", "last", "reader"),
)
async def _conversations_get(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("target", "ts", "fetch", "with_thread_message", "last", "reader"))
    from slackx.storage import get_thread_state

    target = _target_param(params)
    ts = _str_param(params, "ts")
    fetch = _bool_param(params, "fetch", None, nullable=True)
    with_thread_message = bool(_bool_param(params, "with_thread_message", False))
    last = _last_param(params)
    reader = _str_param(params, "reader", default="default", allow_empty=True, nullable=True)

    resolved = await _resolve_target_or_error(ctx, target, ts)

    if resolved.thread_ts is None:
        payload = await _get_channel(ctx, resolved.channel, fetch, last, with_thread_message)
        await _mark_read(ctx, resolved.channel, None, reader)
        return payload

    need_fetch = False
    cached = False
    async with _open_db(ctx.common) as conn:
        cached = get_thread_state(conn, resolved.channel, resolved.thread_ts) is not None
        if _should_fetch(fetch, cached):
            need_fetch = True
        else:
            messages, user_names, channel_name = _load_thread_view(
                conn, resolved.channel, resolved.thread_ts
            )

    if need_fetch:
        async with _open_db(ctx.common) as conn:
            still_missing = get_thread_state(conn, resolved.channel, resolved.thread_ts) is None
        if fetch is True or still_missing:
            await _fetch_thread_view(ctx, resolved.channel, resolved.thread_ts)
        async with _open_db(ctx.common) as conn:
            messages, user_names, channel_name = _load_thread_view(
                conn, resolved.channel, resolved.thread_ts
            )

    from slackx.urls import ThreadRef

    payload = _thread_payload(
        ThreadRef(resolved.channel, resolved.thread_ts),
        messages,
        user_names,
        channel_name,
    )
    await _mark_read(ctx, resolved.channel, resolved.thread_ts, reader)
    return payload


@method(
    "conversations.search",
    "Search Slack, cache the matches, and return them.",
    ("query", "count", "limit", "sort", "sort_dir", "full_threads", "fields"),
)
async def _conversations_search(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(
        params,
        ("query", "count", "limit", "sort", "sort_dir", "full_threads", "fields"),
    )
    from slackx.cache import fetch_search
    from slackx.cli._internal._channels import _channel_id_names
    from slackx.storage import load_user_display_names

    query = _str_param(params, "query", required=True)
    assert query is not None
    count = _int_param(params, "count", 20)
    limit = _int_param(params, "limit", DEFAULT_SEARCH_LIMIT)
    sort = _choice_param(params, "sort", "timestamp", ("score", "timestamp"))
    sort_dir = _choice_param(params, "sort_dir", "desc", ("asc", "desc"))
    full_threads = bool(_bool_param(params, "full_threads", False))
    selected = _fields_param(params, SEARCH_FIELDS, SEARCH_DEFAULT_FIELDS)

    async with _open_client(ctx.common) as client, _open_db(ctx.common, client) as conn:
        result = await fetch_search(
            conn,
            client,
            query=query,
            count=count,
            sort=sort,
            sort_dir=sort_dir,
            full_threads=full_threads,
            limit=limit,
        )
        matches = result.matches
        user_ids = {m.get("user") for m in matches if m.get("user")}
        channel_ids = {m.get("channel") for m in matches if m.get("channel")}
        user_names = load_user_display_names(conn, user_ids)
        channel_names = _channel_id_names(conn, channel_ids)

    payload = _search_payload(query, matches, user_names, channel_names, selected)
    payload["stats"] = {
        "threads_seen": result.threads_seen,
        "threads_new": result.threads_new,
        "messages_seen": result.messages_seen,
        "messages_new": result.messages_new,
    }
    return payload


async def _get_channel(
    ctx: RpcContext,
    channel: str,
    fetch: bool | None,
    last: str,
    with_thread_message: bool,
) -> dict[str, Any]:
    """Load a channel's messages, fetching first when needed (CLI parity)."""
    from slackx.storage import count_channel_messages

    oldest = _oldest_for(last)
    need_fetch = False
    cached = False
    async with _open_db(ctx.common) as conn:
        cached = count_channel_messages(conn, channel) > 0
        if _should_fetch(fetch, cached):
            need_fetch = True
        else:
            messages, user_names, channel_name = _load_channel_view(
                conn, channel, with_thread_message, oldest
            )

    if need_fetch:
        async with _open_db(ctx.common) as conn:
            still_empty = count_channel_messages(conn, channel) == 0
        if fetch is True or still_empty:
            await _fetch_channel_view(ctx, channel, full_threads=with_thread_message, oldest=oldest)
        async with _open_db(ctx.common) as conn:
            messages, user_names, channel_name = _load_channel_view(
                conn, channel, with_thread_message, oldest
            )

    return _channel_payload(channel, messages, user_names, channel_name)


def _should_fetch(fetch: bool | None, cached: bool) -> bool:
    """Decide whether to hit Slack given the fetch flag and cache state."""
    if fetch is None:
        return not cached
    return fetch


# ---------------------------------------------------------------------------
# Read markers
# ---------------------------------------------------------------------------


@method(
    "read.mark",
    "Advance a reader's last-read pointer for a channel or thread.",
    ("target", "ts", "reader", "last_read"),
)
async def _read_mark(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("target", "ts", "reader", "last_read"))
    from slackx.storage import latest_message_ts, set_last_read, transaction

    target = _target_param(params)
    ts = _str_param(params, "ts")
    reader = _str_param(params, "reader", default="default")
    assert reader is not None
    last_read = _str_param(params, "last_read")
    resolved = await _resolve_target_or_error(ctx, target, ts)

    async with _open_db(ctx.common) as conn:
        marker_ts = last_read
        if marker_ts is None:
            marker_ts = latest_message_ts(conn, resolved.channel, resolved.thread_ts)
        if marker_ts is None:
            scope = (
                f"thread {resolved.channel}/{resolved.thread_ts}"
                if resolved.thread_ts is not None
                else f"channel {resolved.channel}"
            )
            raise RpcError(
                SERVER_ERROR,
                f"no cached messages in {scope}; fetch first or pass last_read",
            )
        with transaction(conn):
            marker = set_last_read(conn, reader, resolved.channel, marker_ts, resolved.thread_ts)
    return {"marker": asdict(marker)}


@method(
    "read.show",
    "List stored last-read pointers, optionally filtered by reader or channel.",
    ("reader", "channel"),
)
async def _read_show(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("reader", "channel"))
    from slackx.storage import load_read_markers

    reader = _str_param(params, "reader", allow_empty=True)
    channel = _str_param(params, "channel")
    channel_id = await _resolve_channel_or_error(ctx, channel) if channel else None

    async with _open_db(ctx.common) as conn:
        markers = load_read_markers(conn, reader, channel=channel_id)
    return {"read_count": len(markers), "markers": [asdict(marker) for marker in markers]}


@method(
    "read.clear",
    "Delete a reader's last-read pointers (all, one channel, or one thread).",
    ("reader", "channel", "ts"),
)
async def _read_clear(ctx: RpcContext, params: dict[str, Any]) -> dict[str, Any]:
    _check_params(params, ("reader", "channel", "ts"))
    from slackx.storage import delete_read_marker, delete_read_markers, transaction

    reader = _str_param(params, "reader", required=True)
    assert reader is not None
    channel = _str_param(params, "channel")
    ts = _str_param(params, "ts")
    if ts is not None and channel is None:
        raise RpcError(INVALID_PARAMS, "ts requires channel")

    channel_id = await _resolve_channel_or_error(ctx, channel) if channel else None

    async with _open_db(ctx.common) as conn:
        with transaction(conn):
            if channel_id is None:
                deleted = delete_read_markers(conn, reader)
            elif ts is None:
                deleted = delete_read_markers(conn, reader, channel=channel_id)
            else:
                deleted = delete_read_marker(conn, reader, channel_id, ts)
    return {"deleted": deleted}
