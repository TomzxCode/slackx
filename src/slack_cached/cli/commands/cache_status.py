"""``slackx cache status`` command."""

import json
import sys
from dataclasses import asdict

from slack_cached.cli._internal import _client
from slack_cached.cli._internal._refs import _output_format
from slack_cached.cli._internal._render import _render_status_human
from slack_cached.cli._internal._shared import (
    ApiBaseUrlArg,
    DbArg,
    JsonArg,
    JsonlArg,
    LogLevelArg,
    WorkspaceArg,
    _setup,
    cache_app,
)
from slack_cached.cli._internal._style import _supports_styles
from slack_cached.storage import db_status


@cache_app.command(name="status")
async def status(
    *,
    json_output: JsonArg = False,
    jsonl_output: JsonlArg = False,
    db: DbArg = None,
    workspace: WorkspaceArg = None,
    api_base_url: ApiBaseUrlArg = None,
    log_level: LogLevelArg = "info",
) -> int:
    """Print cache database status: counts and last update per entity."""
    common = _setup(db, api_base_url, log_level, workspace)
    fmt = _output_format(json_output, jsonl_output)
    async with _client._open_db(common) as conn:
        snapshot = db_status(conn)

    if fmt in ("json", "jsonl"):
        sys.stdout.write(
            json.dumps(asdict(snapshot), ensure_ascii=False, indent=2 if fmt == "json" else None)
            + "\n"
        )
    else:
        sys.stdout.write(_render_status_human(snapshot, styled=_supports_styles(sys.stdout)))
    return 0
