"""``slackx users fetch`` command."""

import sys

from slack_cached.cli._internal import _client
from slack_cached.cli._internal._shared import (
    ApiBaseUrlArg,
    DbArg,
    LogLevelArg,
    UserIdArg,
    WorkspaceArg,
    _setup,
    users_app,
)


@users_app.command(name="fetch")
async def fetch(
    user_id: UserIdArg = None,
    *,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Fetch and cache every workspace user, or a single user by id."""
    common = _setup(db, api_base_url, log_level, workspace)

    if user_id is not None:
        return await _fetch_one_user(common, user_id)

    from slack_cached.cache import fetch_users

    async with _client._open_client(common) as client, _client._open_db(common, client) as conn:
        result = await fetch_users(conn, client)
    print(
        f"processed {result.processed} users ({result.added} added, {result.total} total in db)",
        file=sys.stderr,
    )
    return 0


async def _fetch_one_user(common, user_id: str) -> int:
    """Fetch and cache a single user via users.info."""
    import httpx

    from slack_cached.cache import fetch_user
    from slack_cached.slack_api import SlackAPIError

    try:
        async with (
            _client._open_client(common) as client,
            _client._open_db(common, client) as conn,
        ):
            user = await fetch_user(conn, client, user_id)
    except (SlackAPIError, httpx.HTTPError) as exc:
        print(f"error: could not fetch user {user_id}: {exc}", file=sys.stderr)
        return 1

    if user is None:
        print(f"error: user {user_id} not found", file=sys.stderr)
        return 1
    label = user.real_name or user.name or user_id
    print(f"fetched user {user_id} ({label})", file=sys.stderr)
    return 0
