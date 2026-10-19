"""``slackx users get`` command (alias: show)."""

import sys

from slackx._log import get_logger
from slackx.cli._internal import _client
from slackx.cli._internal._fields import (
    USER_DEFAULT_FIELDS,
    USER_FIELDS,
    parse_fields,
)
from slackx.cli._internal._refs import _output_format
from slackx.cli._internal._render import _render_users_human, _render_users_json
from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    DbArg,
    GetFetchArg,
    JsonArg,
    JsonlArg,
    LogLevelArg,
    UserFieldsArg,
    UserTargetArg,
    WorkspaceArg,
    _setup,
    users_app,
)
from slackx.cli._internal._style import _supports_styles
from slackx.storage import CachedUser, get_user

log = get_logger(__name__)


@users_app.command(name="get", alias="show")
async def get(
    user: UserTargetArg,
    *,
    fetch: GetFetchArg = True,
    fields: UserFieldsArg = None,
    json_output: JsonArg = False,
    jsonl_output: JsonlArg = False,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Print one cached user, fetching it from Slack when missing.

    USER is a user id (e.g. U001). A cache miss fetches just that user via
    users.info unless --no-fetch is given.
    """
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)
    try:
        selected = parse_fields(fields, USER_FIELDS, USER_DEFAULT_FIELDS)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    async with _client._open_db(common) as conn:
        cached = get_user(conn, user)

    if cached is None and fetch:
        cached = await _fetch_single_user(common, user)
    if cached is None:
        print(f"error: user {user} is not cached", file=sys.stderr)
        return 1

    users = [cached]
    if fmt in ("json", "jsonl"):
        sys.stdout.write(_render_users_json(users, selected, indent=2 if fmt == "json" else None))
    else:
        sys.stdout.write(_render_users_human(users, selected, styled=_supports_styles(sys.stdout)))
    return 0


async def _fetch_single_user(common, user_id: str) -> CachedUser | None:
    """Fetch one user's profile from Slack, returning it on success."""
    import httpx

    from slackx.cache import fetch_user
    from slackx.slack_api import SlackAPIError

    log.info("user_not_cached_fetching", user=user_id)
    try:
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            return await fetch_user(conn, client, user_id)
    except (SlackAPIError, httpx.HTTPError) as exc:
        print(f"error: could not fetch user {user_id}: {exc}", file=sys.stderr)
        return None
