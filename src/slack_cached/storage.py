"""SQLite storage layer for cached Slack threads.

Schema:

  threads
    channel        TEXT    not null
    thread_ts      TEXT    not null
    last_fetched   REAL    not null    unix epoch seconds
    latest_reply   TEXT    nullable    highest ts seen so far for this thread
    PRIMARY KEY (channel, thread_ts)

  messages
    channel        TEXT    not null
    thread_ts      TEXT    not null    root ts of the thread
    ts             TEXT    not null    this message's ts (unique within thread)
    user           TEXT    nullable
    text           TEXT    nullable
    payload        TEXT    not null    JSON-encoded Slack message: content fields
                                       plus render-only blocks/attachments
    PRIMARY KEY (channel, thread_ts, ts)
    FOREIGN KEY (channel, thread_ts) REFERENCES threads(channel, thread_ts)

  users
    id             TEXT    not null    Slack user id (e.g. U123)
    name           TEXT    nullable    the user's handle (the 'name' field)
    real_name      TEXT    nullable    the user's display/real name
    fetched_at     REAL    not null    unix epoch seconds of last fetch
    payload        TEXT    not null    full JSON-encoded Slack user
    PRIMARY KEY (id)

  channels
    id             TEXT    not null    Slack channel id (e.g. C123)
    name           TEXT    nullable    the channel name (the 'name' field)
    is_private     INTEGER nullable    1 if private, 0 if public, null if unknown
    fetched_at     REAL    not null    unix epoch seconds of last fetch
    payload        TEXT    not null    full JSON-encoded Slack channel
    PRIMARY KEY (id)

  messages_fts
    FTS5 virtual table over messages.text (external content), kept in sync by
    triggers; see SEARCH_SCHEMA and ensure_search_index(). Optional: absent
    when the SQLite build lacks FTS5.
"""

import json
import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import structlog

log = structlog.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    channel       TEXT NOT NULL,
    thread_ts     TEXT NOT NULL,
    last_fetched  REAL NOT NULL,
    latest_reply  TEXT,
    PRIMARY KEY (channel, thread_ts)
);

CREATE TABLE IF NOT EXISTS messages (
    channel    TEXT NOT NULL,
    thread_ts  TEXT NOT NULL,
    ts         TEXT NOT NULL,
    user       TEXT,
    text       TEXT,
    payload    TEXT NOT NULL,
    PRIMARY KEY (channel, thread_ts, ts),
    FOREIGN KEY (channel, thread_ts) REFERENCES threads(channel, thread_ts)
);

CREATE INDEX IF NOT EXISTS idx_messages_thread
    ON messages (channel, thread_ts, ts);

CREATE TABLE IF NOT EXISTS users (
    id          TEXT NOT NULL,
    name        TEXT,
    real_name   TEXT,
    fetched_at  REAL NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_users_fetched_at
    ON users (fetched_at);

CREATE TABLE IF NOT EXISTS channels (
    id          TEXT NOT NULL,
    name        TEXT,
    is_private  INTEGER,
    fetched_at  REAL NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_channels_fetched_at
    ON channels (fetched_at);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT NOT NULL,
    value  TEXT NOT NULL,
    PRIMARY KEY (key)
);
"""

# Full-text search index over message text, kept in sync with the messages
# table by triggers. Kept separate from SCHEMA because FTS5 is technically an
# optional SQLite compile-time feature; a build without it should still be
# able to cache and browse (search just degrades to no results).
SEARCH_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text,
    content='messages',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts (rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts (messages_fts, rowid, text)
    VALUES ('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE OF text ON messages BEGIN
    INSERT INTO messages_fts (messages_fts, rowid, text)
    VALUES ('delete', old.rowid, old.text);
    INSERT INTO messages_fts (rowid, text) VALUES (new.rowid, new.text);
END;
"""


@dataclass(frozen=True)
class ThreadState:
    """Cached state for a thread, used to decide what to refetch."""

    channel: str
    thread_ts: str
    last_fetched: float
    latest_reply: str | None


@dataclass(frozen=True)
class CachedMessage:
    """A single cached Slack message as returned by show()."""

    ts: str
    user: str | None
    text: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class CachedUser:
    """A single cached Slack user."""

    id: str
    name: str | None
    real_name: str | None
    fetched_at: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class CachedChannel:
    """A single cached Slack channel/conversation."""

    id: str
    name: str | None
    is_private: bool | None
    fetched_at: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class ChannelSummary:
    """A cached channel plus aggregate activity counts for listings."""

    id: str
    name: str | None
    is_private: bool | None
    message_count: int
    thread_count: int
    latest_ts: float | None


@dataclass(frozen=True)
class ChannelMessageEntry:
    """A channel message plus the thread it belongs to, for channel views.

    ``thread_ts`` equals ``ts`` for a top-level message and is the root's ts
    for a thread reply, which lets renderers mark replies as threaded.
    """

    ts: str
    user: str | None
    text: str | None
    thread_ts: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ChannelMessage:
    """A thread-root message plus aggregate thread info, for channel views."""

    ts: str
    user: str | None
    text: str | None
    payload: dict[str, Any]
    reply_count: int
    latest_reply_ts: str | None


@dataclass(frozen=True)
class SearchHit:
    """A message matched by FTS search."""

    channel: str
    thread_ts: str
    ts: str
    user: str | None
    text: str | None
    snippet: str | None


@dataclass(frozen=True)
class DbStatus:
    """Aggregate counts and last-update times for the cache database.

    Update times are unix epoch seconds, or None when the corresponding table
    is empty. Channel/user update times come from the ``fetched_at`` column of
    each table; threads/messages report the newest ``threads.last_fetched``
    since messages carry no fetch timestamp of their own.
    """

    channel_count: int
    user_count: int
    thread_count: int
    message_count: int
    channels_updated_at: float | None
    users_updated_at: float | None
    threads_updated_at: float | None


@dataclass(frozen=True)
class ClearedCounts:
    """Number of rows removed by ``clear_cache``, per entity."""

    messages: int
    threads: int
    channels: int
    users: int


def _normalize_sql(statement: str) -> str:
    """Collapse whitespace in a SQL statement for compact logging."""
    return " ".join(statement.split())


def _log_sql(statement: str, duration_s: float) -> None:
    """Log a completed SQL statement and how long it took.

    Emits at debug level, so the statements only surface when debug
    logging is enabled (--log-level debug). The duration is reported in
    milliseconds.
    """
    log.debug(
        "sql",
        statement=_normalize_sql(statement),
        duration_ms=round(duration_s * 1000, 3),
    )


class _LoggingCursor(sqlite3.Cursor):
    """Cursor that logs each executed statement with its duration."""

    def execute(self, sql: str, parameters: Any = (), /) -> Self:
        start = time.perf_counter()
        try:
            return super().execute(sql, parameters)
        finally:
            _log_sql(sql, time.perf_counter() - start)

    def executemany(self, sql: str, seq_of_parameters: Any, /) -> Self:
        start = time.perf_counter()
        try:
            return super().executemany(sql, seq_of_parameters)
        finally:
            _log_sql(sql, time.perf_counter() - start)


class _LoggingConnection(sqlite3.Connection):
    """Connection whose execute helpers go through _LoggingCursor."""

    def cursor(self, factory: Any = None) -> sqlite3.Cursor:
        return super().cursor(factory or _LoggingCursor)

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        cur = self.cursor()
        return cur.execute(sql, parameters)

    def executemany(self, sql: str, parameters: Any, /) -> sqlite3.Cursor:
        cur = self.cursor()
        return cur.executemany(sql, parameters)

    def executescript(self, sql_script: str, /) -> sqlite3.Cursor:
        start = time.perf_counter()
        try:
            cur = sqlite3.Connection.cursor(self)
            return cur.executescript(sql_script)
        finally:
            _log_sql(sql_script, time.perf_counter() - start)


def connect(db_path: Path) -> sqlite3.Connection:
    """Open (and initialize) the SQLite database at db_path."""
    log.debug("db_connect_start", db_path=str(db_path))

    start = time.perf_counter()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    log.debug("db_mkdir_done", duration_ms=round((time.perf_counter() - start) * 1000, 3))

    start = time.perf_counter()
    conn = sqlite3.connect(db_path, factory=_LoggingConnection)
    conn.row_factory = sqlite3.Row
    log.debug("db_open_done", duration_ms=round((time.perf_counter() - start) * 1000, 3))

    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _ensure_fts_schema(conn)

    log.debug("db_connect_done", db_path=str(db_path))
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a block inside a transaction, committing on success."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_thread_state(conn: sqlite3.Connection, channel: str, thread_ts: str) -> ThreadState | None:
    """Return the cached state for the given thread, or None if missing."""
    row = conn.execute(
        "SELECT channel, thread_ts, last_fetched, latest_reply "
        "FROM threads WHERE channel = ? AND thread_ts = ?",
        (channel, thread_ts),
    ).fetchone()
    if row is None:
        return None
    return ThreadState(
        channel=row["channel"],
        thread_ts=row["thread_ts"],
        last_fetched=row["last_fetched"],
        latest_reply=row["latest_reply"],
    )


def upsert_messages(
    conn: sqlite3.Connection,
    channel: str,
    thread_ts: str,
    messages: Iterable[dict[str, Any]],
) -> int:
    """Insert or replace messages for a thread; returns the number of rows
    actually modified (new inserts plus updates whose content changed).

    Two serializations are involved. The ``payload`` column stores the stable
    content fields (see ``_MESSAGE_CONTENT_FIELDS``) plus the render-only
    ``blocks``/``attachments`` (``_RENDER_FIELDS``), so the web UI can render
    the links and buttons that bot messages carry only inside blocks. Change
    detection reduces both the incoming message and the cached row back to
    their canonical content projection (``_canonical_message_payload``):
    blocks/attachments decorate the same message differently across endpoints
    (block_id drift, signed image URLs), so they must not affect it. Rows
    stored by older slackx versions lack blocks entirely; the first refetch
    that sees blocks for such a row rewrites it once to backfill them, after
    which the row is stable again.
    """
    msg_list = list(messages)
    if not msg_list:
        return 0

    stored_fields = _MESSAGE_CONTENT_FIELDS | _RENDER_FIELDS
    rows = [
        (
            channel,
            thread_ts,
            msg["ts"],
            msg.get("user"),
            msg.get("text"),
            _stored_message_payload(msg),
        )
        for msg in msg_list
    ]

    stripped: set[str] = set()
    for msg in msg_list:
        stripped.update(k for k in msg if k not in stored_fields)
    if stripped:
        log.debug(
            "upsert_messages_stripped_fields",
            channel=channel,
            thread_ts=thread_ts,
            count=len(rows),
            fields=sorted(stripped),
        )

    # Decide which rows to write by comparing content projections with the
    # cache. The payload column may hold legacy rows without blocks (written
    # by older versions) as well as current ones; both reduce to the same
    # canonical projection, so a plain string compare is not enough.
    existing = _existing_payloads(conn, channel, thread_ts, [row[2] for row in rows])
    to_write = []
    for msg, row in zip(msg_list, rows, strict=True):
        old_payload = existing.get(row[2])
        if _content_changed(old_payload, msg):
            to_write.append(row)
            # When debug logging is on, surface the field-level diff between
            # the incoming canonical payload and what is already cached. This
            # makes cache oscillation against real Slack diagnosable with
            # --log-level debug.
            if old_payload is not None and log.is_enabled_for(10):  # logging.DEBUG
                _log_content_diff(channel, thread_ts, row[2], msg, old_payload)

    if not to_write:
        return 0

    cursor = conn.executemany(
        "INSERT INTO messages "
        "(channel, thread_ts, ts, user, text, payload) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(channel, thread_ts, ts) DO UPDATE SET "
        "  user = excluded.user, "
        "  text = excluded.text, "
        "  payload = excluded.payload",
        to_write,
    )
    return cursor.rowcount or 0


def mark_channel_roots_deleted_not_in(
    conn: sqlite3.Connection,
    channel: str,
    keep_ts: Iterable[str],
    oldest: str | None = None,
) -> int:
    """Flag cached thread-root messages that Slack no longer returns.

    Slack omits deleted messages from history responses, so absence after a
    complete pass over the window means deletion. The rows are kept and
    marked in their payload (``deleted: true``) instead of removed, so the
    archive preserves what was said; the web UI renders them with a
    "(deleted)" annotation. Only root rows (``ts = thread_ts``) in the window
    bounded by ``oldest`` are considered, matching what the fetch covered.
    Returns the number of rows newly marked.
    """
    keep = set(keep_ts)
    sql = "SELECT ts FROM messages WHERE channel = ? AND ts = thread_ts"
    params: list[Any] = [channel]
    if oldest is not None:
        sql += " AND CAST(ts AS REAL) >= CAST(? AS REAL)"
        params.append(oldest)
    stale = [
        row["ts"]
        for row in conn.execute(sql, params).fetchall()
        if row["ts"] not in keep
    ]
    return _mark_messages_deleted(conn, channel, stale)


def mark_thread_messages_deleted_not_in(
    conn: sqlite3.Connection,
    channel: str,
    thread_ts: str,
    keep_ts: Iterable[str],
) -> int:
    """Flag cached messages of one thread that Slack no longer returns.

    Scope is every row of the thread (replies and the parent row), so this
    must only be called after a complete fetch of the thread. Returns the
    number of rows newly marked.
    """
    keep = set(keep_ts)
    stale = [
        row["ts"]
        for row in conn.execute(
            "SELECT ts FROM messages WHERE channel = ? AND thread_ts = ?",
            (channel, thread_ts),
        ).fetchall()
        if row["ts"] not in keep
    ]
    return _mark_messages_deleted(conn, channel, stale)


def _mark_messages_deleted(
    conn: sqlite3.Connection,
    channel: str,
    ts_values: list[str],
) -> int:
    """Set ``deleted: true`` in the payload of the named rows.

    The flag lives in the payload JSON rather than a column so no schema
    migration is needed; content (text, blocks, ...) is preserved untouched
    and the FTS index keeps matching the original text.
    """
    if not ts_values:
        return 0
    placeholders = ",".join("?" * len(ts_values))
    rows = conn.execute(
        f"SELECT ts, payload FROM messages "
        f"WHERE channel = ? AND ts IN ({placeholders})",
        (channel, *ts_values),
    ).fetchall()
    updates = []
    for row in rows:
        payload = json.loads(row["payload"])
        if payload.get("deleted"):
            continue
        payload["deleted"] = True
        updates.append((json.dumps(payload, ensure_ascii=False, sort_keys=True), row["ts"]))
    if not updates:
        return 0
    cursor = conn.executemany(
        "UPDATE messages SET payload = ? WHERE channel = ? AND ts = ?",
        [(payload, channel, ts) for payload, ts in updates],
    )
    return cursor.rowcount or 0


_DIFF_VALUE_PREVIEW = 160


def _existing_payloads(
    conn: sqlite3.Connection,
    channel: str,
    thread_ts: str,
    ts_values: list[str],
) -> dict[str, str]:
    """Return {ts: raw payload JSON} for the cached rows named by ts_values.

    On a query error (corrupt database, bound-variable limits) returns an
    empty map, which makes every row look changed and get rewritten.
    """
    if not ts_values:
        return {}
    placeholders = ",".join("?" * len(ts_values))
    try:
        rows = conn.execute(
            f"SELECT ts, payload FROM messages "
            f"WHERE channel = ? AND thread_ts = ? AND ts IN ({placeholders})",
            (channel, thread_ts, *ts_values),
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {row["ts"]: row["payload"] for row in rows}


def _content_changed(stored_payload: str | None, msg: dict[str, Any]) -> bool:
    """Decide whether ``msg`` must be written over the cached row.

    ``stored_payload`` is the raw JSON held in the payload column, which may
    or may not carry blocks/attachments depending on the slackx version that
    wrote it. Content is compared on the canonical projection of both sides;
    render-only fields additionally trigger a one-time backfill write when
    the incoming message has them and the stored row does not.
    """
    if stored_payload is None:
        return True
    try:
        stored = json.loads(stored_payload)
    except (TypeError, ValueError):
        return True
    if _canonical_message_payload(stored) != _canonical_message_payload(msg):
        return True
    return any(k in msg and k not in stored for k in _RENDER_FIELDS)


def _log_content_diff(
    channel: str,
    thread_ts: str,
    ts: str,
    msg: dict[str, Any],
    old_payload: str,
) -> None:
    """Log a field-level diff between incoming content and the cached row.

    Compares the canonical content projections (render-only fields excluded)
    and emits a ``message_payload_diff`` event with the changes, so cache
    oscillation between endpoints is observable. Emits nothing when the
    projections agree (e.g. the change was only a blocks backfill).
    """
    try:
        old = json.loads(old_payload)
    except (TypeError, ValueError):
        return
    old_canonical = {k: v for k, v in old.items() if k in _MESSAGE_CONTENT_FIELDS}
    new_canonical = {k: v for k, v in msg.items() if k in _MESSAGE_CONTENT_FIELDS}
    added = sorted(set(new_canonical) - set(old_canonical))
    removed = sorted(set(old_canonical) - set(new_canonical))
    changed = sorted(
        k for k in set(new_canonical) & set(old_canonical) if new_canonical[k] != old_canonical[k]
    )
    if not (added or removed or changed):
        return
    log.debug(
        "message_payload_diff",
        channel=channel,
        thread_ts=thread_ts,
        ts=ts,
        added=added,
        removed=removed,
        changed={
            k: (
                _preview(old_canonical.get(k)),
                _preview(new_canonical.get(k)),
            )
            for k in changed
        },
    )


def _preview(value: Any) -> str:
    """Render a JSON-serializable preview of ``value`` for log output."""
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(rendered) > _DIFF_VALUE_PREVIEW:
        return rendered[:_DIFF_VALUE_PREVIEW] + "..."
    return rendered


_MESSAGE_CONTENT_FIELDS = frozenset(
    {
        # Identity. We deliberately exclude ``type`` (Slack returns "message"
        # from some endpoints and "im" from others for the same DM message),
        # ``thread_ts`` and ``parent_user_id`` (present on ``conversations.*``
        # but absent from ``search.messages`` for thread parents; ``thread_ts``
        # is also part of the cache key), and ``edited`` (present on
        # ``conversations.replies`` but absent from ``search.messages``).
        # The actual edit is reflected in ``text``, so we still detect edits.
        "subtype",
        "ts",
        # Authorship.
        "user",
        "bot_id",
        "app_id",
        # Content body. ``text`` already reflects edits. ``text`` IS also
        # subject to search-highlighting drift (matched terms get wrapped
        # in backticks by ``search.messages``); ``fetch_search`` avoids that
        # by not caching matches directly when ``--full-threads`` is set.
        "text",
    }
)

# Fields kept in the stored payload so the web UI can render bot-message
# links (which live only in blocks/attachments) and "(edited)" annotations,
# but excluded from change detection because they drift between endpoints
# without any content change (see _MESSAGE_CONTENT_FIELDS for the
# endpoint-drift details).
_RENDER_FIELDS = frozenset({"blocks", "attachments", "edited"})


def _canonical_message_payload(msg: dict[str, Any]) -> str:
    """Serialize the stable content fields of ``msg``, sorted and stable.

    Slack decorates the same message differently depending on which endpoint
    returned it (``channel``/``permalink`` from ``search.messages``, ``team``
    metadata from ``conversations.*``, ``reply_count``/``latest_reply`` that
    drifts as threads grow, per-user ``last_read``, signed URLs in
    ``files``/``attachments``, etc.). Comparing on the full payload would
    oscillate every run. Whitelisting only the stable, content-bearing fields
    keeps the comparison stable across endpoints and over time.
    """
    return _project_message(msg, _MESSAGE_CONTENT_FIELDS)


def _stored_message_payload(msg: dict[str, Any]) -> str:
    """Serialize ``msg`` for the payload column: content plus render fields.

    Same stable serialization as ``_canonical_message_payload`` but also
    keeps ``blocks``/``attachments`` so the web UI can render links that
    bot messages carry only inside blocks.
    """
    return _project_message(msg, _MESSAGE_CONTENT_FIELDS | _RENDER_FIELDS)


def _project_message(msg: dict[str, Any], fields: frozenset[str]) -> str:
    canonical = {k: v for k, v in msg.items() if k in fields}
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True)


def record_thread_refresh(
    conn: sqlite3.Connection,
    channel: str,
    thread_ts: str,
    latest_reply: str | None,
    now: float | None = None,
) -> None:
    """Insert or update the thread row to record this refresh."""
    ts_now = time.time() if now is None else now
    conn.execute(
        "INSERT INTO threads (channel, thread_ts, last_fetched, latest_reply) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(channel, thread_ts) DO UPDATE SET "
        "  last_fetched = excluded.last_fetched, "
        "  latest_reply = excluded.latest_reply",
        (channel, thread_ts, ts_now, latest_reply),
    )


def load_thread_messages(
    conn: sqlite3.Connection, channel: str, thread_ts: str
) -> list[CachedMessage]:
    """Return all cached messages for a thread, ordered chronologically by ts."""
    rows = conn.execute(
        "SELECT ts, user, text, payload FROM messages "
        "WHERE channel = ? AND thread_ts = ? "
        "ORDER BY CAST(ts AS REAL) ASC",
        (channel, thread_ts),
    ).fetchall()
    return [
        CachedMessage(
            ts=row["ts"],
            user=row["user"],
            text=row["text"],
            payload=json.loads(row["payload"]),
        )
        for row in rows
    ]


def count_messages(conn: sqlite3.Connection, channel: str, thread_ts: str) -> int:
    """Return the number of cached messages for a thread."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM messages WHERE channel = ? AND thread_ts = ?",
        (channel, thread_ts),
    ).fetchone()
    return int(row["n"]) if row else 0


def upsert_users(
    conn: sqlite3.Connection,
    users: Iterable[dict[str, Any]],
    now: float | None = None,
) -> int:
    """Insert or replace users; returns the count written."""
    fetched_at = time.time() if now is None else now
    rows = [
        (
            user["id"],
            user.get("name"),
            user.get("real_name") or (user.get("profile") or {}).get("real_name"),
            fetched_at,
            json.dumps(user, ensure_ascii=False, sort_keys=True),
        )
        for user in users
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO users "
        "(id, name, real_name, fetched_at, payload) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def upsert_channels(
    conn: sqlite3.Connection,
    channels: Iterable[dict[str, Any]],
    now: float | None = None,
) -> int:
    """Insert or replace channels; returns the count written."""
    fetched_at = time.time() if now is None else now
    rows = [
        (
            channel["id"],
            channel.get("name"),
            _bool_to_int(channel.get("is_private")),
            fetched_at,
            json.dumps(channel, ensure_ascii=False, sort_keys=True),
        )
        for channel in channels
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO channels "
        "(id, name, is_private, fetched_at, payload) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def get_user(conn: sqlite3.Connection, user_id: str) -> CachedUser | None:
    """Return the cached user with the given id, or None if missing."""
    row = conn.execute(
        "SELECT id, name, real_name, fetched_at, payload FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return _row_to_user(row) if row is not None else None


def get_channel(conn: sqlite3.Connection, channel_id: str) -> CachedChannel | None:
    """Return the cached channel with the given id, or None if missing."""
    row = conn.execute(
        "SELECT id, name, is_private, fetched_at, payload FROM channels WHERE id = ?",
        (channel_id,),
    ).fetchone()
    return _row_to_channel(row) if row is not None else None


def load_users(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    include_payload: bool = True,
) -> list[CachedUser]:
    """Return cached users, ordered by id.

    Pass ``limit`` to cap the number of rows returned (pushed into SQL so a
    small listing does not read the whole table), and ``include_payload=False``
    to skip reading and JSON-decoding the large payload column when it is not
    going to be rendered.
    """
    columns = "id, name, real_name, fetched_at" + (", payload" if include_payload else "")
    sql = f"SELECT {columns} FROM users ORDER BY id ASC"
    params: list[Any] = []
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_user(row, include_payload=include_payload) for row in rows]


def load_user_display_names(conn: sqlite3.Connection, user_ids: Iterable[str]) -> dict[str, str]:
    """Return a {user_id: display_name} map for just the requested users.

    This avoids loading and JSON-decoding every user's full payload: only the
    denormalized name columns of the rows matching user_ids are read, so cost
    scales with the thread's participants rather than the whole workspace.

    The display name is formatted as "Real name (handle)" when both are known.
    When only one is present that value is used alone, and when neither is known
    the value falls back to the id.
    """
    ids = list(dict.fromkeys(user_ids))
    if not ids:
        return {}
    names: dict[str, str] = {}
    # Chunk to stay well under SQLite's bound-variable limit (default 999).
    for start in range(0, len(ids), 900):
        chunk = ids[start : start + 900]
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT id, name, real_name FROM users WHERE id IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            names[row["id"]] = _format_display_name(row["real_name"], row["name"], row["id"])
    return names


def find_user_by_handle(conn: sqlite3.Connection, handle: str) -> str | None:
    """Return the id of the cached user whose handle matches ``handle``.

    Matching is case-insensitive against the user's ``name`` (handle). Returns
    None when no cached user matches.
    """
    row = conn.execute(
        "SELECT id FROM users WHERE lower(name) = lower(?) LIMIT 1",
        (handle,),
    ).fetchone()
    return row["id"] if row else None


def _format_display_name(real_name: str | None, name: str | None, user_id: str) -> str:
    """Combine a user's real name and handle into "Real name (handle)".

    Falls back to whichever single value is available, and finally to the id.
    """
    if real_name and name:
        return f"{real_name} ({name})"
    return real_name or name or user_id


def load_channels(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    include_payload: bool = True,
) -> list[CachedChannel]:
    """Return cached channels, ordered by id.

    Pass ``limit`` to cap the number of rows returned (pushed into SQL so a
    small listing does not read the whole table), and ``include_payload=False``
    to skip reading and JSON-decoding the large payload column when it is not
    going to be rendered. Note that the ``is_private``-derived "direct"
    visibility relies on ``payload``; callers that need it must keep the
    payload.
    """
    columns = "id, name, is_private, fetched_at" + (", payload" if include_payload else "")
    sql = f"SELECT {columns} FROM channels ORDER BY id ASC"
    params: list[Any] = []
    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_channel(row, include_payload=include_payload) for row in rows]


def load_channel_display_names(
    conn: sqlite3.Connection, channel_ids: Iterable[str]
) -> dict[str, str]:
    """Return a {channel_id: display_name} map for the requested channels.

    Regular channels resolve to their stored name. Direct message channels
    (nameless conversations whose payload marks ``is_im``) resolve to the
    display name of the peer user stored on the conversation, so a DM shows
    up as the other person instead of its raw ``D...`` id. Channels that
    cannot be resolved (absent from the cache, or an IM whose peer user is
    unknown) are omitted, leaving callers to fall back to the channel id.
    """
    ids = list(dict.fromkeys(cid for cid in channel_ids if cid))
    if not ids:
        return {}
    names: dict[str, str] = {}
    im_peers: list[tuple[str, str]] = []
    # Chunk to stay well under SQLite's bound-variable limit (default 999).
    for start in range(0, len(ids), 900):
        chunk = ids[start : start + 900]
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT id, name, payload FROM channels WHERE id IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            if row["name"]:
                names[row["id"]] = row["name"]
                continue
            payload = json.loads(row["payload"]) if row["payload"] else {}
            peer_id = payload.get("user")
            if payload.get("is_im") and peer_id:
                im_peers.append((row["id"], peer_id))
    if im_peers:
        peer_names = load_user_display_names(conn, [peer for _, peer in im_peers])
        for channel_id, peer_id in im_peers:
            if peer_id in peer_names:
                names[channel_id] = peer_names[peer_id]
    return names


def load_im_channel_ids(conn: sqlite3.Connection, channel_ids: Iterable[str]) -> set[str]:
    """Return the subset of channel_ids that are direct message conversations.

    A channel is a DM when its cached payload marks ``is_im``; the id prefix
    is not trusted because Slack uses ``D`` ids only for one-to-one messages.
    """
    ids = list(dict.fromkeys(cid for cid in channel_ids if cid))
    if not ids:
        return set()
    im_ids: set[str] = set()
    # Chunk to stay well under SQLite's bound-variable limit (default 999).
    for start in range(0, len(ids), 900):
        chunk = ids[start : start + 900]
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT id, payload FROM channels WHERE id IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload"]) if row["payload"] else {}
            if payload.get("is_im"):
                im_ids.add(row["id"])
    return im_ids


def find_im_channel_for_user(conn: sqlite3.Connection, user_id: str) -> str | None:
    """Return the cached direct-message channel id with ``user_id``, if any.

    A channel is a DM when its cached payload marks ``is_im``; the peer user is
    stored in the payload's ``user`` field.
    """
    rows = conn.execute("SELECT id, payload FROM channels").fetchall()
    for row in rows:
        payload = json.loads(row["payload"]) if row["payload"] else {}
        if payload.get("is_im") and payload.get("user") == user_id:
            return row["id"]
    return None


def count_users(conn: sqlite3.Connection) -> int:
    """Return the number of cached users."""
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return int(row["n"]) if row else 0


def count_channels(conn: sqlite3.Connection) -> int:
    """Return the number of cached channels."""
    row = conn.execute("SELECT COUNT(*) AS n FROM channels").fetchone()
    return int(row["n"]) if row else 0


def load_channel_messages(
    conn: sqlite3.Connection,
    channel: str,
    oldest: str | None = None,
    *,
    include_thread_replies: bool = False,
) -> list[ChannelMessageEntry]:
    """Return a channel's messages, ordered chronologically.

    By default only top-level messages are returned; thread replies (messages
    whose ts differs from their thread root) are excluded so this reflects the
    channel as it appears in Slack, not the replies nested under each message.
    Pass ``include_thread_replies=True`` to include replies, each tagged with
    its thread root via ``thread_ts``.
    """
    where = "channel = ?"
    params: list[Any] = [channel]
    if not include_thread_replies:
        where += " AND ts = thread_ts"
    if oldest is not None:
        where += " AND CAST(ts AS REAL) >= CAST(? AS REAL)"
        params.append(oldest)
    rows = conn.execute(
        f"SELECT ts, user, text, thread_ts, payload FROM messages "
        f"WHERE {where} ORDER BY CAST(ts AS REAL) ASC",
        params,
    ).fetchall()
    return [
        ChannelMessageEntry(
            ts=row["ts"],
            user=row["user"],
            text=row["text"],
            thread_ts=row["thread_ts"],
            payload=json.loads(row["payload"]),
        )
        for row in rows
    ]


def count_channel_messages(conn: sqlite3.Connection, channel: str) -> int:
    """Return the number of cached messages for a channel (across all threads)."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM messages WHERE channel = ?",
        (channel,),
    ).fetchone()
    return int(row["n"]) if row else 0


def count_all_messages(conn: sqlite3.Connection) -> int:
    """Return the number of cached messages across every channel."""
    row = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()
    return int(row["n"]) if row else 0


def count_all_threads(conn: sqlite3.Connection) -> int:
    """Return the number of cached threads across every channel."""
    row = conn.execute("SELECT COUNT(*) AS n FROM threads").fetchone()
    return int(row["n"]) if row else 0


def clear_cache(
    conn: sqlite3.Connection,
    *,
    messages: bool = False,
    channels: bool = False,
    users: bool = False,
) -> ClearedCounts:
    """Delete cached rows for the requested entities; returns what was removed.

    Clearing ``messages`` also clears the ``threads`` table: thread rows are the
    "is this cached" signal that ``show`` keys on, so leaving them behind would
    make an emptied thread look cached and suppress a refetch. The FTS index is
    kept in sync by the ``messages_fts`` delete trigger.
    """
    cleared_messages = 0
    cleared_threads = 0
    cleared_channels = 0
    cleared_users = 0
    with transaction(conn):
        if messages:
            cleared_messages = conn.execute("DELETE FROM messages").rowcount
            cleared_threads = conn.execute("DELETE FROM threads").rowcount
        if channels:
            cleared_channels = conn.execute("DELETE FROM channels").rowcount
        if users:
            cleared_users = conn.execute("DELETE FROM users").rowcount
    return ClearedCounts(
        messages=cleared_messages,
        threads=cleared_threads,
        channels=cleared_channels,
        users=cleared_users,
    )


def db_status(conn: sqlite3.Connection) -> DbStatus:
    """Return counts and last-update times for the cache database."""
    row = conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM channels) AS channel_count, "
        "(SELECT COUNT(*) FROM users) AS user_count, "
        "(SELECT COUNT(*) FROM threads) AS thread_count, "
        "(SELECT COUNT(*) FROM messages) AS message_count, "
        "(SELECT MAX(fetched_at) FROM channels) AS channels_updated_at, "
        "(SELECT MAX(fetched_at) FROM users) AS users_updated_at, "
        "(SELECT MAX(last_fetched) FROM threads) AS threads_updated_at"
    ).fetchone()
    return DbStatus(
        channel_count=row["channel_count"],
        user_count=row["user_count"],
        thread_count=row["thread_count"],
        message_count=row["message_count"],
        channels_updated_at=row["channels_updated_at"],
        users_updated_at=row["users_updated_at"],
        threads_updated_at=row["threads_updated_at"],
    )


def ensure_search_index(conn: sqlite3.Connection) -> bool:
    """Backfill the FTS search index once, covering rows written before it existed.

    Returns True when full-text search is usable. The index schema and sync
    triggers are (re)created by connect(), so every writer keeps the index up
    to date; the rebuild here only handles databases populated by older
    versions of slackx, tracked via a marker row in the meta table.
    """
    present = conn.execute(
        "SELECT COUNT(*) AS n FROM sqlite_master WHERE name = 'messages_fts'"
    ).fetchone()["n"]
    if not present:
        log.warning("fts5_unavailable")
        return False
    marker = conn.execute("SELECT value FROM meta WHERE key = 'fts_backfilled'").fetchone()
    if marker is None:
        log.info("fts_rebuild_start")
        conn.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild')")
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('fts_backfilled', '1')")
        conn.commit()
        log.info("fts_rebuild_done")
    return True


def _ensure_fts_schema(conn: sqlite3.Connection) -> None:
    """Create the FTS index and its sync triggers if FTS5 is available.

    Runs on every connect so that every writer (CLI or server) keeps the
    search index up to date. Degrades to a warning when the SQLite build
    lacks FTS5.
    """
    try:
        conn.executescript(SEARCH_SCHEMA)
    except sqlite3.OperationalError as exc:
        log.warning("fts5_unavailable", error=str(exc))


def _fts_query(raw: str) -> str:
    """Sanitize free text into a safe FTS5 query.

    Each whitespace-separated term is quoted (defusing FTS5 query syntax such
    as NEAR, OR or column filters) and turned into a prefix match. Terms are
    implicitly ANDed by FTS5.
    """
    terms = []
    for term in raw.split():
        cleaned = term.replace('"', " ").strip()
        if cleaned:
            terms.append(f'"{cleaned}"*')
    return " ".join(terms)


def search_messages(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[SearchHit]:
    """Full-text search cached messages, best matches first.

    Returns an empty list when the query has no usable terms or when the FTS5
    index is unavailable (see ensure_search_index).
    """
    fts_query = _fts_query(query)
    if not fts_query:
        return []
    try:
        rows = conn.execute(
            "SELECT m.channel, m.thread_ts, m.ts, m.user, m.text, "
            "snippet(messages_fts, 0, '[', ']', '…', 16) AS snippet "
            "FROM messages_fts f "
            "JOIN messages m ON m.rowid = f.rowid "
            "WHERE messages_fts MATCH ? "
            "ORDER BY rank "
            "LIMIT ?",
            (fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        log.warning("search_failed", query=query, error=str(exc))
        return []
    return [
        SearchHit(
            channel=row["channel"],
            thread_ts=row["thread_ts"],
            ts=row["ts"],
            user=row["user"],
            text=row["text"],
            snippet=row["snippet"],
        )
        for row in rows
    ]


def list_channel_summaries(conn: sqlite3.Connection) -> list[ChannelSummary]:
    """Return every cached channel with message/thread counts and last activity.

    Channels without cached messages still appear, with zero counts.
    """
    rows = conn.execute(
        "SELECT c.id, c.name, c.is_private, "
        "COUNT(m.ts) AS message_count, "
        "COUNT(DISTINCT m.thread_ts) AS thread_count, "
        "MAX(CAST(m.ts AS REAL)) AS latest "
        "FROM channels c LEFT JOIN messages m ON m.channel = c.id "
        "GROUP BY c.id, c.name, c.is_private "
        "ORDER BY c.name COLLATE NOCASE ASC, c.id ASC"
    ).fetchall()
    return [
        ChannelSummary(
            id=row["id"],
            name=row["name"],
            is_private=None if row["is_private"] is None else bool(row["is_private"]),
            message_count=row["message_count"],
            thread_count=row["thread_count"],
            latest_ts=row["latest"],
        )
        for row in rows
    ]


def load_channel_thread_roots(
    conn: sqlite3.Connection,
    channel: str,
    before: str | None = None,
    limit: int = 200,
) -> list[ChannelMessage]:
    """Return cached thread-root messages for a channel, newest first.

    Each result carries the number of stored replies and the ts of the latest
    reply. ``before`` (a message ts) pages backwards in time.
    """
    sql = (
        "SELECT m.ts, m.user, m.text, m.payload, "
        "(SELECT COUNT(*) FROM messages r "
        " WHERE r.channel = m.channel AND r.thread_ts = m.thread_ts "
        " AND r.ts != m.ts) AS reply_count, "
        "(SELECT r.ts FROM messages r "
        " WHERE r.channel = m.channel AND r.thread_ts = m.thread_ts "
        " AND r.ts != m.ts "
        " ORDER BY CAST(r.ts AS REAL) DESC LIMIT 1) AS latest_reply_ts "
        "FROM messages m "
        "WHERE m.channel = ? AND m.ts = m.thread_ts"
    )
    params: list[Any] = [channel]
    if before is not None:
        sql += " AND CAST(m.ts AS REAL) < CAST(? AS REAL)"
        params.append(before)
    sql += " ORDER BY CAST(m.ts AS REAL) DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [
        ChannelMessage(
            ts=row["ts"],
            user=row["user"],
            text=row["text"],
            payload=json.loads(row["payload"]),
            reply_count=row["reply_count"],
            latest_reply_ts=row["latest_reply_ts"],
        )
        for row in rows
    ]


def _bool_to_int(value: Any) -> int | None:
    """Map a Slack boolean-ish value to 0/1, preserving None."""
    if value is None:
        return None
    return 1 if value else 0


def _row_to_user(row: sqlite3.Row, *, include_payload: bool = True) -> CachedUser:
    return CachedUser(
        id=row["id"],
        name=row["name"],
        real_name=row["real_name"],
        fetched_at=row["fetched_at"],
        payload=json.loads(row["payload"]) if include_payload else {},
    )


def _row_to_channel(row: sqlite3.Row, *, include_payload: bool = True) -> CachedChannel:
    is_private = row["is_private"]
    return CachedChannel(
        id=row["id"],
        name=row["name"],
        is_private=None if is_private is None else bool(is_private),
        fetched_at=row["fetched_at"],
        payload=json.loads(row["payload"]) if include_payload else {},
    )
