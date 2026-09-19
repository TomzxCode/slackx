"""Shared CLI infrastructure: the cyclopts app, parameter aliases, and setup helpers."""

import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import structlog
from cyclopts import App, Parameter

log = structlog.get_logger(__name__)

app = App(
    name="slackx",
    help="Cache Slack threads to a local SQLite database.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Shared parameter annotations (kept once so every command stays in sync)
# ---------------------------------------------------------------------------

DbArg = Annotated[
    Path | None,
    Parameter(help="SQLite cache path (default: per-workspace, under the cache dir)."),
]
WorkspaceArg = Annotated[
    str | None,
    Parameter(
        help="Workspace name selecting the per-workspace cache database "
        "(~/.cache/slackx/WORKSPACE/threads.db). Discovered automatically via "
        "auth.test when omitted.",
    ),
]
ApiBaseUrlArg = Annotated[
    str | None,
    Parameter(
        help="Slack API base URL (default: https://slack.com/api, use "
        "http://localhost:PORT/api for the fake server). Can also be set via "
        "the SLACK_API_BASE_URL environment variable.",
    ),
]
LogLevelArg = Annotated[
    Literal["debug", "info", "warning", "error", "critical"],
    Parameter(
        name="--log-level",
        help="Logging verbosity: debug, info, warning, error, or critical "
        "(default: info). Use 'debug' for per-query SQL timings.",
    ),
]
JsonArg = Annotated[
    bool,
    Parameter(name="--json", help="Render output as pretty-printed JSON."),
]
JsonlArg = Annotated[
    bool,
    Parameter(
        name="--jsonl",
        help="Render output as a single compact JSON line (no indentation). "
        "Convenient for piping into jq -c, wc -l, or appending to a .jsonl file.",
    ),
]
FetchArg = Annotated[
    bool,
    Parameter(
        name="--fetch",
        help="Auto-fetch from Slack when the cache is empty (disable with --no-fetch).",
    ),
]
LimitArg = Annotated[
    int,
    Parameter(
        name="--limit",
        help="Maximum number of entries to return (default: all; 0 for all).",
    ),
]
UserFieldsArg = Annotated[
    str | None,
    Parameter(
        name="--fields",
        help="Comma-separated fields to include, in order: id, name, real_name, "
        "fetched_at, payload (default: id,name,real_name).",
    ),
]
ChannelFieldsArg = Annotated[
    str | None,
    Parameter(
        name="--fields",
        help="Comma-separated fields to include, in order: id, name, is_private, "
        "display_name, fetched_at, payload (default: id,name,is_private).",
    ),
]
SearchFieldsArg = Annotated[
    str | None,
    Parameter(
        name="--fields",
        help="Comma-separated fields to include, in order: channel, channel_name, "
        "ts, thread_ts, user, user_name, text, permalink, payload (default: "
        "channel,channel_name,ts,thread_ts,user,user_name,text,permalink).",
    ),
]
UrlArg = Annotated[
    str | None,
    Parameter(
        help="Slack permalink: a thread (e.g. "
        "https://acme.slack.com/archives/C123/p1700000000123456) or a channel "
        "(e.g. https://acme.slack.com/archives/C123).",
    ),
]
ChannelArg = Annotated[
    str | None,
    Parameter(
        help="Slack channel id (e.g. C001), bare name (e.g. general), or "
        "'#'-prefixed name (e.g. #general). Names are resolved against the "
        "cached channels. Used with --ts, or alone to target a whole channel.",
    ),
]
TsArg = Annotated[
    str | None,
    Parameter(help="Thread root ts (e.g. 1700000000.123456), used with --channel."),
]


@dataclass
class CommonArgs:
    """Carries the shared db/workspace/api-base-url/log-level flags through helpers."""

    db: Path | None = None
    workspace: str | None = None
    api_base_url: str | None = None
    log_level: str = "info"


def _configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper())
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def _setup(
    db: Path | None, api_base_url: str | None, log_level: str, workspace: str | None = None
) -> CommonArgs:
    """Build the CommonArgs carrier and wire up logging in one place."""
    common = CommonArgs(db=db, workspace=workspace, api_base_url=api_base_url, log_level=log_level)
    _configure_logging(log_level)
    log.debug("dispatch")
    return common


@contextmanager
def _timed(phase: str, **fields: object) -> Iterator[None]:
    """Log how long a block of work takes, at debug level.

    Surfaces only at debug log level, alongside the per-query SQL timings, so
    the time spent outside the database (deserialization, rendering, output) can
    be attributed to a specific phase.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        log.debug(
            "phase",
            phase=phase,
            duration_ms=round((time.perf_counter() - start) * 1000, 3),
            **fields,
        )
