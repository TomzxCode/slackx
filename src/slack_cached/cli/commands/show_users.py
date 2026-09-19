"""``slackx show-users`` command."""

import sys

import structlog

from slack_cached.cli._internal import _client
from slack_cached.cli._internal._fields import (
    USER_DEFAULT_FIELDS,
    USER_FIELDS,
    parse_fields,
)
from slack_cached.cli._internal._refs import _output_format
from slack_cached.cli._internal._render import _render_users_human, _render_users_json
from slack_cached.cli._internal._shared import (
    ApiBaseUrlArg,
    DbArg,
    FetchArg,
    JsonArg,
    JsonlArg,
    LimitArg,
    LogLevelArg,
    UserFieldsArg,
    UserIdArg,
    WorkspaceArg,
    _setup,
    app,
)
from slack_cached.storage import get_user, load_users

log = structlog.get_logger(__name__)


@app.command(name="show-users")
async def show_users(
    user_id: UserIdArg = None,
    *,
    fetch: FetchArg = True,
    limit: LimitArg = 0,
    fields: UserFieldsArg = None,
    json_output: JsonArg = False,
    jsonl_output: JsonlArg = False,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Print cached users to stdout (human-readable by default).

    Pass a user id to show only that user; it is fetched from Slack (via
    users.info) when not cached, unless --no-fetch is given.
    """
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)
    try:
        selected = parse_fields(fields, USER_FIELDS, USER_DEFAULT_FIELDS)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    include_payload = "payload" in selected

    async with _client._open_db(common) as conn:
        users = _load_selected(conn, user_id, limit, include_payload)

    if user_id is not None:
        if not users and fetch:
            users = await _fetch_single_user(common, user_id)
        if not users:
            print(f"error: user {user_id} is not cached", file=sys.stderr)
            return 1
    elif not users and fetch:
        from slack_cached.cache import fetch_users

        log.info("users_not_cached_fetching")
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            if not load_users(conn, limit=1):
                await fetch_users(conn, client)
            users = load_users(conn, limit=limit, include_payload=include_payload)

    if fmt in ("json", "jsonl"):
        sys.stdout.write(_render_users_json(users, selected, indent=2 if fmt == "json" else None))
    else:
        sys.stdout.write(_render_users_human(users, selected))
    return 0


def _load_selected(conn, user_id: str | None, limit: int, include_payload: bool):
    """Load one user by id, or every cached user when id is None."""
    if user_id is None:
        return load_users(conn, limit=limit, include_payload=include_payload)
    user = get_user(conn, user_id)
    return [user] if user is not None else []


async def _fetch_single_user(common, user_id: str):
    """Fetch one user's profile from Slack, returning it on success."""
    import httpx

    from slack_cached.cache import fetch_user
    from slack_cached.slack_api import SlackAPIError

    log.info("user_not_cached_fetching", user=user_id)
    try:
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            user = await fetch_user(conn, client, user_id)
    except (SlackAPIError, httpx.HTTPError) as exc:
        print(f"error: could not fetch user {user_id}: {exc}", file=sys.stderr)
        return []
    return [user] if user is not None else []
