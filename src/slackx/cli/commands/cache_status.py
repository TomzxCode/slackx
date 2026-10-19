"""``slackx cache status`` command."""

import json
import sys
from dataclasses import asdict

from slackx.cli._internal import _client
from slackx.cli._internal._refs import _output_format
from slackx.cli._internal._render import _render_status_human
from slackx.cli._internal._shared import (
    ApiBaseUrlArg,
    DbArg,
    JsonArg,
    JsonlArg,
    LogLevelArg,
    WorkspaceArg,
    _setup,
    cache_app,
)
from slackx.cli._internal._style import _supports_styles
from slackx.storage import db_status
from slackx.workspace import workspace_name_from_db_path


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
    db_path = await _client._resolve_db_path(common)
    with _client._open_db_at(db_path) as conn:
        snapshot = db_status(conn)
    workspace_name = workspace_name_from_db_path(db_path)

    if fmt in ("json", "jsonl"):
        payload = {
            "workspace": workspace_name,
            "db_path": str(db_path),
            **asdict(snapshot),
        }
        sys.stdout.write(
            json.dumps(payload, ensure_ascii=False, indent=2 if fmt == "json" else None) + "\n"
        )
    else:
        styled = _supports_styles(sys.stdout)
        sys.stdout.write(
            _render_status_human(snapshot, workspace=workspace_name, db_path=db_path, styled=styled)
        )
    return 0
