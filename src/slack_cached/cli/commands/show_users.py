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
    WorkspaceArg,
    _setup,
    app,
)
from slack_cached.storage import load_users

log = structlog.get_logger(__name__)


@app.command(name="show-users")
async def show_users(
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
    """Print cached users to stdout (human-readable by default)."""
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)
    try:
        selected = parse_fields(fields, USER_FIELDS, USER_DEFAULT_FIELDS)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    async with _client._open_db(common) as conn:
        users = load_users(conn)

    if not users and fetch:
        from slack_cached.cache import fetch_users

        log.info("users_not_cached_fetching")
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            if not load_users(conn):
                await fetch_users(conn, client)
            users = load_users(conn)

    if limit > 0:
        users = users[:limit]

    if fmt in ("json", "jsonl"):
        sys.stdout.write(_render_users_json(users, selected, indent=2 if fmt == "json" else None))
    else:
        sys.stdout.write(_render_users_human(users, selected))
    return 0
