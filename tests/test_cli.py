"""Tests for the CLI surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slack_cached import cli
from slack_cached.cache import FetchResult
from slack_cached.config import Credentials as Creds


class StubClient:
    pass


def _populate_single_message(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    """Cache a single-message thread via a stub client."""

    class FakeClient:
        async def iter_thread_replies(
            self,
            channel: str,
            thread_ts: str,
            oldest: str | None = None,
            limit: int = 200,
        ):
            yield {"ts": "1700000000.000100", "user": "U1", "text": "hello"}

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeClient())

    rc = cli.main(
        [
            "conversations",
            "fetch",
            "C0123ABCDEF",
            "--ts",
            "1700000000.000100",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0


def test_show_prints_human_readable_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Show defaults to human-readable output without hitting Slack."""
    db_path = tmp_path / "cache.db"
    _populate_single_message(monkeypatch, db_path)

    # --no-fetch ensures we don't call the client again.
    rc = cli.main(
        [
            "conversations",
            "show",
            "C0123ABCDEF",
            "--ts",
            "1700000000.000100",
            "--db",
            str(db_path),
            "--no-fetch",
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    # Should be human-readable text, not JSON.
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    assert "C0123ABCDEF/1700000000.000100" in out
    assert "1 message(s)" in out
    assert "U1" in out
    assert "hello" in out


def test_show_renders_user_name_when_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Show resolves a message's user id to a cached display name."""
    db_path = tmp_path / "cache.db"
    _populate_single_message(monkeypatch, db_path)

    # Cache a user whose id matches the message author (U1).
    class FakeUsers:
        async def iter_users(self, limit: int = 1000):
            yield {
                "id": "U1",
                "name": "alice",
                "real_name": "Alice Smith",
            }

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeUsers())
    assert cli.main(["users", "fetch", "--db", str(db_path)]) == 0

    rc = cli.main(
        [
            "conversations",
            "show",
            "C0123ABCDEF",
            "--ts",
            "1700000000.000100",
            "--db",
            str(db_path),
            "--no-fetch",
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    # The author is shown as "Real name (handle)", not the raw user id.
    assert "] Alice Smith (alice)" in out
    assert "hello" in out


def test_show_prints_json_with_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Show emits JSON when --json is passed."""
    db_path = tmp_path / "cache.db"
    _populate_single_message(monkeypatch, db_path)

    rc = cli.main(
        [
            "conversations",
            "show",
            "C0123ABCDEF",
            "--ts",
            "1700000000.000100",
            "--db",
            str(db_path),
            "--no-fetch",
            "--json",
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["channel"] == "C0123ABCDEF"
    assert payload["thread_ts"] == "1700000000.000100"
    assert payload["message_count"] == 1
    assert payload["messages"][0]["text"] == "hello"


def test_show_prints_jsonl_with_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Show emits the whole thread as a single JSON line with --jsonl."""
    db_path = tmp_path / "cache.db"
    _populate_single_message(monkeypatch, db_path)

    rc = cli.main(
        [
            "conversations",
            "show",
            "C0123ABCDEF",
            "--ts",
            "1700000000.000100",
            "--db",
            str(db_path),
            "--no-fetch",
            "--jsonl",
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    # Output is exactly one JSON document on a single line (plus trailing newline).
    lines = out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["channel"] == "C0123ABCDEF"
    assert payload["thread_ts"] == "1700000000.000100"
    assert payload["message_count"] == 1
    assert payload["messages"][0]["text"] == "hello"


def test_show_json_and_jsonl_are_mutually_exclusive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--json and --jsonl cannot be combined."""
    with pytest.raises(SystemExit):
        cli.main(
            [
                "conversations",
                "show",
                "C1",
                "--ts",
                "1.0",
                "--db",
                str(tmp_path / "cache.db"),
                "--json",
                "--jsonl",
            ]
        )
    err = capsys.readouterr().err
    assert "mutually exclusive" in err


def test_fetch_with_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    calls: list[str | None] = []

    class FakeClient:
        async def iter_thread_replies(
            self,
            channel: str,
            thread_ts: str,
            oldest: str | None = None,
            limit: int = 200,
        ):
            calls.append(oldest)
            yield {"ts": thread_ts, "user": "U1", "text": "root"}

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeClient())

    rc = cli.main(
        [
            "conversations",
            "fetch",
            "https://acme.slack.com/archives/C0123ABCDEF/p1700000000123456",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0
    assert calls == [None]


def test_resolve_ref_requires_url_or_channel_ts() -> None:
    with pytest.raises(SystemExit):
        cli._internal._refs._resolve_ref(None, None, None)


def test_fetch_result_dataclass_fields() -> None:
    result = FetchResult(
        channel="C1", thread_ts="1.000", fetched_messages=1, total_messages=2, incremental=True
    )
    assert result.incremental is True
    assert result.total_messages == 2


class FakeListClient:
    """Stub client returning fixed user/channel lists."""

    async def iter_users(self, limit: int = 1000):
        yield {"id": "U1", "name": "alice", "real_name": "Alice Smith"}

    async def iter_channels(self, types: str = "public_channel", limit: int = 1000):
        yield {"id": "C1", "name": "general", "is_private": False}

    async def get_channel_info(self, channel: str):
        if channel == "C1":
            return {"id": "C1", "name": "general", "is_private": False}
        raise AssertionError(f"unexpected channel {channel}")

    async def get_user_info(self, user: str):
        if user == "U1":
            return {"id": "U1", "name": "alice", "real_name": "Alice Smith"}
        raise AssertionError(f"unexpected user {user}")

    async def aclose(self) -> None:
        pass


def test_fetch_users_then_show(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["users", "fetch", "--db", str(db_path)])
    assert rc == 0

    rc = cli.main(["users", "list", "--db", str(db_path), "--no-fetch"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 user(s)" in out
    assert "U1" in out
    assert "alice" in out
    assert "Alice Smith" in out


def test_fetch_users_single(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """users fetch with an id fetches just that user via users.info."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["users", "fetch", "U1", "--db", str(db_path)])
    assert rc == 0
    assert "fetched user U1 (Alice Smith)" in capsys.readouterr().err

    rc = cli.main(["users", "list", "U1", "--db", str(db_path), "--no-fetch"])
    assert rc == 0
    assert "alice" in capsys.readouterr().out


class UnknownUserClient:
    """Stub client that reports every user lookup as empty."""

    async def get_user_info(self, user: str):
        return {}

    async def aclose(self) -> None:
        pass


def test_fetch_users_single_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """users fetch with an unknown id reports an error and exits non-zero."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: UnknownUserClient())

    rc = cli.main(["users", "fetch", "U9", "--db", str(db_path)])
    assert rc == 1
    assert "error: user U9 not found" in capsys.readouterr().err


def test_show_users_single_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """users list with an id shows only that cached user."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())
    assert cli.main(["users", "fetch", "--db", str(db_path)]) == 0

    rc = cli.main(["users", "list", "U1", "--db", str(db_path), "--no-fetch"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 user(s)" in out
    assert "U1" in out
    assert "alice" in out


def test_show_users_single_fetches_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """users list with an uncached id fetches it via users.info."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["users", "list", "U1", "--db", str(db_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["user_count"] == 1
    assert payload["users"][0]["id"] == "U1"
    assert payload["users"][0]["name"] == "alice"


def test_show_users_single_unknown_no_fetch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """users list with an uncached id and --no-fetch reports an error."""
    db_path = tmp_path / "cache.db"
    rc = cli.main(["users", "list", "U9", "--db", str(db_path), "--no-fetch"])
    assert rc == 1
    assert "error: user U9 is not cached" in capsys.readouterr().err


def test_show_users_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["users", "list", "--db", str(db_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["user_count"] == 1
    assert payload["users"][0]["id"] == "U1"
    assert payload["users"][0]["name"] == "alice"


def test_show_users_jsonl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """users list --jsonl emits a single compact JSON line."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["users", "list", "--db", str(db_path), "--jsonl"])
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["user_count"] == 1
    assert payload["users"][0]["id"] == "U1"
    assert payload["users"][0]["name"] == "alice"


def test_fetch_channels_then_show(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["channels", "fetch", "--db", str(db_path)])
    assert rc == 0

    rc = cli.main(["channels", "list", "--db", str(db_path), "--no-fetch"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 channel(s)" in out
    assert "C1" in out
    assert "general" in out
    assert "public" in out


def test_fetch_channels_single(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """channels fetch with an id fetches just that channel via conversations.info."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["channels", "fetch", "C1", "--db", str(db_path)])
    assert rc == 0
    assert "fetched channel C1 (general)" in capsys.readouterr().err

    rc = cli.main(["channels", "list", "C1", "--db", str(db_path), "--no-fetch"])
    assert rc == 0
    assert "general" in capsys.readouterr().out


class UnknownChannelClient:
    """Stub client that reports every channel lookup as empty."""

    async def get_channel_info(self, channel: str):
        return {}

    async def aclose(self) -> None:
        pass


def test_fetch_channels_single_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """channels fetch with an unknown id reports an error and exits non-zero."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: UnknownChannelClient())

    rc = cli.main(["channels", "fetch", "C9", "--db", str(db_path)])
    assert rc == 1
    assert "error: channel C9 not found" in capsys.readouterr().err


def test_show_channels_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["channels", "list", "--db", str(db_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["channel_count"] == 1
    assert payload["channels"][0]["id"] == "C1"
    assert payload["channels"][0]["is_private"] is False


def test_show_channels_jsonl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """channels list --jsonl emits a single compact JSON line."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["channels", "list", "--db", str(db_path), "--jsonl"])
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["channel_count"] == 1
    assert payload["channels"][0]["id"] == "C1"
    assert payload["channels"][0]["is_private"] is False


def test_show_channels_single_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """channels list with an id shows only that cached channel."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())
    assert cli.main(["channels", "fetch", "--db", str(db_path)]) == 0

    rc = cli.main(["channels", "list", "C1", "--db", str(db_path), "--no-fetch"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 channel(s)" in out
    assert "C1" in out
    assert "general" in out


def test_show_channels_single_fetches_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """channels list with an uncached id fetches it via conversations.info."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeListClient())

    rc = cli.main(["channels", "list", "C1", "--db", str(db_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["channel_count"] == 1
    assert payload["channels"][0]["id"] == "C1"
    assert payload["channels"][0]["name"] == "general"


def test_show_channels_single_unknown_no_fetch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """channels list with an uncached id and --no-fetch reports an error."""
    db_path = tmp_path / "cache.db"
    rc = cli.main(["channels", "list", "C9", "--db", str(db_path), "--no-fetch"])
    assert rc == 1
    assert "error: channel C9 is not cached" in capsys.readouterr().err


def test_show_users_no_fetch_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "cache.db"
    rc = cli.main(["users", "list", "--db", str(db_path), "--no-fetch"])
    assert rc == 0
    assert "0 user(s)" in capsys.readouterr().out


def test_log_level_debug_emits_debug_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    rc = cli.main(["users", "list", "--db", str(db_path), "--no-fetch", "--log-level", "debug"])
    assert rc == 0
    assert "[debug" in capsys.readouterr().err


def test_log_level_rejects_unknown_value(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    with pytest.raises(SystemExit):
        cli.main(["users", "list", "--db", str(db_path), "--no-fetch", "--log-level", "bogus"])


class FakeMultiListClient:
    """Stub client returning several users and channels."""

    async def iter_users(self, limit: int = 1000):
        yield {"id": "U1", "name": "alice", "real_name": "Alice Smith"}
        yield {"id": "U2", "name": "bob", "real_name": "Bob Jones"}
        yield {"id": "U3", "name": "carol"}

    async def iter_channels(self, types: str = "public_channel", limit: int = 1000):
        yield {"id": "C1", "name": "general", "is_private": False}
        yield {"id": "C2", "name": "random", "is_private": False}
        yield {"id": "C3", "name": "secret", "is_private": True}

    async def aclose(self) -> None:
        pass


def _populate_lists(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeMultiListClient())
    assert cli.main(["users", "fetch", "--db", str(db_path)]) == 0
    assert cli.main(["channels", "fetch", "--db", str(db_path)]) == 0


def test_show_users_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    _populate_lists(monkeypatch, db_path)

    rc = cli.main(["users", "list", "--db", str(db_path), "--no-fetch", "--limit", "2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 user(s)" in out
    assert "U1" in out and "U2" in out
    assert "U3" not in out


def test_show_users_limit_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    _populate_lists(monkeypatch, db_path)

    rc = cli.main(["users", "list", "--db", str(db_path), "--no-fetch", "--json", "--limit", "1"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["user_count"] == 1
    assert payload["users"][0]["id"] == "U1"


def test_show_users_fields_human(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    _populate_lists(monkeypatch, db_path)

    rc = cli.main(["users", "list", "--db", str(db_path), "--no-fetch", "--fields", "id,name"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "U1  alice" in out
    assert "Alice Smith" not in out


def test_show_users_fields_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    _populate_lists(monkeypatch, db_path)

    rc = cli.main(
        ["users", "list", "--db", str(db_path), "--no-fetch", "--json", "--fields", "id,real_name"]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["users"][0] == {"id": "U1", "real_name": "Alice Smith"}


def test_show_users_invalid_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    _populate_lists(monkeypatch, db_path)

    rc = cli.main(["users", "list", "--db", str(db_path), "--no-fetch", "--fields", "bogus"])
    assert rc == 2
    assert "unknown field(s): bogus" in capsys.readouterr().err


def test_show_channels_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    _populate_lists(monkeypatch, db_path)

    rc = cli.main(["channels", "list", "--db", str(db_path), "--no-fetch", "--limit", "2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 channel(s)" in out
    assert "C1" in out and "C2" in out
    assert "C3" not in out


def test_show_channels_fields_human(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    _populate_lists(monkeypatch, db_path)

    rc = cli.main(
        ["channels", "list", "--db", str(db_path), "--no-fetch", "--fields", "id,is_private"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "C3  (private)" in out
    assert "secret" not in out


def test_show_channels_fields_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    _populate_lists(monkeypatch, db_path)

    rc = cli.main(
        [
            "channels",
            "list",
            "--db",
            str(db_path),
            "--no-fetch",
            "--json",
            "--fields",
            "id,display_name",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["channels"][0] == {"id": "C1", "display_name": "general"}


def _populate_status_db(db_path: Path) -> None:
    from slack_cached import storage

    conn = storage.connect(db_path)
    storage.upsert_users(conn, [{"id": "U1", "name": "alice"}], now=1700000000.0)
    storage.upsert_channels(
        conn, [{"id": "C1", "name": "general", "is_private": False}], now=1700000100.0
    )
    storage.record_thread_refresh(conn, "C1", "1700000200.000100", None, now=1700000200.0)
    storage.upsert_messages(
        conn,
        "C1",
        "1700000200.000100",
        [{"ts": "1700000200.000100", "user": "U1", "text": "hi"}],
    )
    conn.commit()
    conn.close()


def test_status_human(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """status prints counts and last update times without hitting Slack."""
    db_path = tmp_path / "cache.db"
    _populate_status_db(db_path)

    rc = cli.main(["cache", "status", "--db", str(db_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 channel(s)" in out
    assert "1 user(s)" in out
    assert "1 thread(s)" in out
    assert "1 message(s)" in out
    assert "2023-11-14" in out


def test_status_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "cache.db"
    _populate_status_db(db_path)

    rc = cli.main(["cache", "status", "--db", str(db_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["channel_count"] == 1
    assert payload["user_count"] == 1
    assert payload["thread_count"] == 1
    assert payload["message_count"] == 1
    assert payload["channels_updated_at"] == 1700000100.0
    assert payload["users_updated_at"] == 1700000000.0
    assert payload["threads_updated_at"] == 1700000200.0


def test_status_jsonl(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """status --jsonl emits a single compact JSON line."""
    db_path = tmp_path / "cache.db"

    rc = cli.main(["cache", "status", "--db", str(db_path), "--jsonl"])
    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["channel_count"] == 0
    assert payload["channels_updated_at"] is None


class FakeChannelClient:
    """Stub client for channel message fetching."""

    def __init__(self, messages=None, thread_replies=None):
        self._messages = messages or []
        self._thread_replies = thread_replies or {}

    async def iter_channel_history(self, channel, oldest=None, latest=None, limit=200):
        for m in self._messages:
            yield m

    async def iter_thread_replies(self, channel, thread_ts, oldest=None, limit=200):
        for m in self._thread_replies.get(thread_ts, []):
            yield m

    async def iter_channels(self, types="public_channel", limit=1000):
        yield {"id": "C1", "name": "general", "is_private": False}

    async def aclose(self) -> None:
        pass


def _threaded_channel_client() -> FakeChannelClient:
    """Client with a threaded parent, one reply, and a standalone message."""
    return FakeChannelClient(
        messages=[
            {
                "ts": "1700000000.000100",
                "user": "U1",
                "text": "parent",
                "thread_ts": "1700000000.000100",
                "reply_count": 1,
                "latest_reply": "1700000000.000200",
            },
            {"ts": "1700000000.000300", "user": "U3", "text": "standalone"},
        ],
        thread_replies={
            "1700000000.000100": [
                {
                    "ts": "1700000000.000100",
                    "user": "U1",
                    "text": "parent",
                    "thread_ts": "1700000000.000100",
                },
                {
                    "ts": "1700000000.000200",
                    "user": "U2",
                    "text": "reply",
                    "thread_ts": "1700000000.000100",
                },
            ],
        },
    )


def test_fetch_channel_messages_basic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[
            {"ts": "1700000000.000100", "user": "U1", "text": "hello"},
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "fetch", "C1", "--db", str(db_path)])
    assert rc == 0


def test_fetch_channel_via_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[
            {"ts": "1700000000.000100", "user": "U1", "text": "hello"},
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(
        [
            "conversations",
            "fetch",
            "--url",
            "https://acme.slack.com/archives/C1",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0


def test_fetch_channel_requires_url_or_channel_ts(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    with pytest.raises(SystemExit):
        cli.main(["conversations", "fetch", "--db", str(db_path)])


def test_fetch_channel_messages_full_threads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[
            {
                "ts": "1700000000.000100",
                "user": "U1",
                "text": "parent",
                "thread_ts": "1700000000.000100",
                "reply_count": 1,
                "latest_reply": "1700000000.000200",
            },
        ],
        thread_replies={
            "1700000000.000100": [
                {
                    "ts": "1700000000.000100",
                    "user": "U1",
                    "text": "parent",
                    "thread_ts": "1700000000.000100",
                },
                {"ts": "1700000000.000200", "user": "U2", "text": "reply"},
            ],
        },
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(
        [
            "conversations",
            "fetch",
            "C1",
            "--full-threads",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0


class FakeChannelClientWithHistory:
    """Stub client that records oldest passed to iter_channel_history."""

    def __init__(self, messages=None):
        self._messages = messages or []
        self.oldest_seen: str | None = "unset"

    async def iter_channel_history(self, channel, oldest=None, latest=None, limit=200):
        self.oldest_seen = oldest
        for m in self._messages:
            yield m

    async def iter_thread_replies(self, channel, thread_ts, oldest=None, limit=200):
        return
        yield  # pragma: no cover - make this an async generator

    async def aclose(self) -> None:
        pass


def test_fetch_channel_default_last_is_one_day(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClientWithHistory(
        messages=[{"ts": "1700000000.000100", "user": "U1", "text": "hello"}]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "fetch", "C1", "--db", str(db_path)])
    assert rc == 0
    assert client.oldest_seen is not None


def test_fetch_channel_last_zero_fetches_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClientWithHistory(
        messages=[{"ts": "1700000000.000100", "user": "U1", "text": "hello"}]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "fetch", "C1", "--last", "all", "--db", str(db_path)])
    assert rc == 0
    assert client.oldest_seen is None


def test_parse_duration() -> None:
    from datetime import timedelta

    parse = cli._internal._duration._parse_duration
    assert parse("24h") == timedelta(hours=24)
    assert parse("1d") == timedelta(days=1)
    assert parse("2d5h30m") == timedelta(days=2, hours=5, minutes=30)
    assert parse("90m") == timedelta(minutes=90)
    assert parse("5h23m13s") == timedelta(hours=5, minutes=23, seconds=13)
    assert parse("all") is None
    assert parse("ALL") is None

    with pytest.raises(ValueError, match="invalid duration"):
        parse("abc")
    with pytest.raises(ValueError, match="invalid duration"):
        parse("")


def test_show_channel_without_ts_human(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[
            {"ts": "1700000000.000100", "user": "U1", "text": "hello"},
            {"ts": "1700000000.000200", "user": "U2", "text": "world"},
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "show", "C1", "--db", str(db_path)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "Channel C1" in out
    assert "2 message(s)" in out


def test_show_channel_via_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[
            {"ts": "1700000000.000100", "user": "U1", "text": "hello"},
            {"ts": "1700000000.000200", "user": "U2", "text": "world"},
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(
        [
            "conversations",
            "show",
            "--url",
            "https://acme.slack.com/archives/C1",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    assert "Channel C1" in out
    assert "2 message(s)" in out
    assert "U1" in out
    assert "hello" in out
    assert "U2" in out
    assert "world" in out


def test_show_channel_excludes_thread_replies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """conversations show --channel renders top-level messages only, not thread replies."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(
        cli._internal._client, "_build_client", lambda args: _threaded_channel_client()
    )

    rc = cli.main(["conversations", "fetch", "C1", "--full-threads", "--db", str(db_path)])
    assert rc == 0

    rc = cli.main(["conversations", "show", "C1", "--db", str(db_path), "--no-fetch", "--json"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    texts = [m["text"] for m in payload["messages"]]
    assert texts == ["parent", "standalone"]
    assert "reply" not in texts


def test_show_channel_with_thread_message_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--with-thread-message includes replies, flagged with their thread root."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(
        cli._internal._client, "_build_client", lambda args: _threaded_channel_client()
    )

    assert cli.main(["conversations", "fetch", "C1", "--full-threads", "--db", str(db_path)]) == 0

    rc = cli.main(
        [
            "conversations",
            "show",
            "C1",
            "--with-thread-message",
            "--db",
            str(db_path),
            "--no-fetch",
            "--json",
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    texts = [m["text"] for m in payload["messages"]]
    assert texts == ["parent", "reply", "standalone"]

    by_text = {m["text"]: m for m in payload["messages"]}
    assert by_text["parent"]["thread_ts"] == "1700000000.000100"
    assert by_text["parent"]["is_thread_reply"] is False
    assert by_text["reply"]["thread_ts"] == "1700000000.000100"
    assert by_text["reply"]["is_thread_reply"] is True
    assert by_text["standalone"]["is_thread_reply"] is False


def test_show_channel_with_thread_message_human(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The human render marks thread replies as part of their thread."""
    db_path = tmp_path / "cache.db"
    monkeypatch.setattr(
        cli._internal._client, "_build_client", lambda args: _threaded_channel_client()
    )

    assert cli.main(["conversations", "fetch", "C1", "--full-threads", "--db", str(db_path)]) == 0

    rc = cli.main(
        [
            "conversations",
            "show",
            "C1",
            "--with-thread-message",
            "--db",
            str(db_path),
            "--no-fetch",
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    assert "3 message(s) (1 thread replie(s))" in out
    assert "reply" in out
    assert "\u21b3" in out
    assert "(thread 1700000000.000100)" in out


def test_show_channel_without_ts_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[
            {"ts": "1700000000.000100", "user": "U1", "text": "hello"},
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "show", "C1", "--db", str(db_path), "--json"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["channel"] == "C1"
    assert payload["message_count"] == 1
    assert payload["messages"][0]["text"] == "hello"


def test_show_channel_without_ts_jsonl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`conversations show --channel --jsonl` emits a single compact JSON line."""
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[
            {"ts": "1700000000.000100", "user": "U1", "text": "hello"},
            {"ts": "1700000000.000200", "user": "U2", "text": "world"},
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "show", "C1", "--db", str(db_path), "--jsonl"])
    assert rc == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["channel"] == "C1"
    assert payload["message_count"] == 2
    assert payload["messages"][0]["text"] == "hello"
    assert payload["messages"][1]["text"] == "world"


def test_show_channel_without_ts_uses_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[
            {"ts": "1700000000.000100", "user": "U1", "text": "cached_msg"},
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "fetch", "C1", "--db", str(db_path)])
    assert rc == 0

    class NoCallClient:
        async def iter_channel_history(self, *a, **kw):
            raise AssertionError("should not fetch")

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: NoCallClient())

    rc = cli.main(["conversations", "show", "C1", "--db", str(db_path), "--no-fetch"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "cached_msg" in out


def test_show_channel_with_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[
            {"ts": "1700000000.000100", "user": "U1", "text": "hello"},
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["channels", "fetch", "--db", str(db_path)])
    assert rc == 0

    rc = cli.main(["conversations", "fetch", "C1", "--db", str(db_path)])
    assert rc == 0

    rc = cli.main(["conversations", "show", "C1", "--db", str(db_path), "--no-fetch"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "general" in out


class DirectChannelClient(FakeChannelClient):
    """Stub client whose only channel is a direct message with user U9."""

    async def iter_channels(self, types="public_channel", limit=1000):
        # Like real Slack, IM conversations carry no name, only the peer.
        yield {"id": "D1", "is_im": True, "user": "U9"}

    async def iter_users(self, limit: int = 1000):
        yield {"id": "U9", "name": "tomzx", "real_name": "Tom Rochette"}


def test_show_direct_channel_resolves_peer_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A direct channel shows its peer user's name, not the raw D id."""
    db_path = tmp_path / "cache.db"
    client = DirectChannelClient(
        messages=[{"ts": "1700000000.000100", "user": "U9", "text": "hello"}]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: client)

    rc = cli.main(["users", "fetch", "--db", str(db_path)])
    assert rc == 0
    rc = cli.main(["channels", "fetch", "--db", str(db_path)])
    assert rc == 0
    rc = cli.main(["conversations", "fetch", "D1", "--db", str(db_path)])
    assert rc == 0

    rc = cli.main(["conversations", "show", "D1", "--db", str(db_path), "--no-fetch"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "Channel Tom Rochette (tomzx)" in out
    assert "Channel D1" not in out


def test_show_direct_channel_json_resolves_peer_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cache.db"
    client = DirectChannelClient(
        messages=[{"ts": "1700000000.000100", "user": "U9", "text": "hello"}]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: client)

    rc = cli.main(["users", "fetch", "--db", str(db_path)])
    assert rc == 0
    rc = cli.main(["channels", "fetch", "--db", str(db_path)])
    assert rc == 0
    rc = cli.main(["conversations", "fetch", "D1", "--db", str(db_path)])
    assert rc == 0

    rc = cli.main(["conversations", "show", "D1", "--db", str(db_path), "--no-fetch", "--json"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["channel"] == "D1"
    assert payload["channel_name"] == "Tom Rochette (tomzx)"


def test_show_channels_labels_direct_channels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """channels list renders direct channels with their peer's name."""
    db_path = tmp_path / "cache.db"
    client = DirectChannelClient()
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: client)

    rc = cli.main(["users", "fetch", "--db", str(db_path)])
    assert rc == 0
    rc = cli.main(["channels", "fetch", "--db", str(db_path)])
    assert rc == 0

    rc = cli.main(["channels", "list", "--db", str(db_path), "--no-fetch"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "D1  Tom Rochette (tomzx)  (direct)" in out


def test_show_channel_resolves_bare_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """conversations show --channel <name> resolves the name to an id via the cached channels."""
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[{"ts": "1700000000.000100", "user": "U1", "text": "hello"}]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    assert cli.main(["channels", "fetch", "--db", str(db_path)]) == 0
    capsys.readouterr()  # clear seeding output

    rc = cli.main(["conversations", "show", "general", "--db", str(db_path)])
    assert rc == 0

    out = capsys.readouterr().out
    # 'hello' is the message that FakeChannelClient serves for C1; reaching it
    # proves the bare name was resolved to C1.
    assert "hello" in out
    assert "1 message(s)" in out


def test_show_channel_resolves_hash_prefixed_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """conversations show --channel #<name> resolves the '#'-prefixed name to an id."""
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[{"ts": "1700000000.000100", "user": "U1", "text": "hello"}]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    assert cli.main(["channels", "fetch", "--db", str(db_path)]) == 0
    capsys.readouterr()

    rc = cli.main(["conversations", "show", "#general", "--db", str(db_path)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "hello" in out
    assert "1 message(s)" in out


def test_fetch_channel_resolves_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """conversations fetch --channel <name> resolves the name and fetches that channel."""
    db_path = tmp_path / "cache.db"
    client = FakeChannelClient(
        messages=[{"ts": "1700000000.000100", "user": "U1", "text": "hello"}]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    assert cli.main(["channels", "fetch", "--db", str(db_path)]) == 0
    capsys.readouterr()

    rc = cli.main(["conversations", "fetch", "general", "--db", str(db_path)])
    assert rc == 0

    err = capsys.readouterr().err
    # The summary reports the resolved channel id, not the input name.
    assert "for C1" in err


def test_fetch_thread_resolves_channel_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """conversations fetch <name> --ts <ts> resolves the name before fetching the thread."""

    class FakeThreadClient:
        async def iter_thread_replies(self, channel, thread_ts, oldest=None, limit=200):
            # The resolver must have turned '#general' into the id 'C1'.
            assert channel == "C1", f"expected resolved id C1, got {channel!r}"
            yield {"ts": "1700000000.000100", "user": "U1", "text": "hello"}

        async def iter_channels(self, types="public_channel", limit=1000):
            yield {"id": "C1", "name": "general", "is_private": False}

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: FakeThreadClient())

    db_path = tmp_path / "cache.db"
    assert cli.main(["channels", "fetch", "--db", str(db_path)]) == 0
    capsys.readouterr()

    rc = cli.main(
        [
            "conversations",
            "fetch",
            "#general",
            "--ts",
            "1700000000.000100",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0


def test_show_channel_unresolved_name_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """conversations show --channel <unknown> errors out and returns 1."""

    class EmptyClient:
        async def iter_channels(self, types="public_channel", limit=1000):
            return
            yield  # pragma: no cover - make this an async generator

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: EmptyClient())

    db_path = tmp_path / "cache.db"
    rc = cli.main(["conversations", "show", "#nope", "--db", str(db_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "could not resolve" in err
    assert "nope" in err


class FakeSearchClient:
    """Stub client returning fixed search matches."""

    def __init__(self, matches=None, thread_replies=None):
        self._matches = matches or []
        self._thread_replies = thread_replies or {}
        self.search_calls = []

    async def iter_search_messages(
        self,
        query,
        count=20,
        sort="timestamp",
        sort_dir="desc",
        limit=200,
    ):
        self.search_calls.append(
            {"query": query, "count": count, "sort": sort, "sort_dir": sort_dir, "limit": limit}
        )
        for i, m in enumerate(self._matches):
            if 0 < limit <= i:
                return
            yield m

    async def iter_thread_replies(self, channel, thread_ts, oldest=None, limit=200):
        for m in self._thread_replies.get((channel, thread_ts), []):
            yield m

    async def aclose(self) -> None:
        pass


def test_search_human_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Search prints human-readable matches and caches them."""
    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(
        matches=[
            {
                "ts": "1700000000.000100",
                "thread_ts": "1700000000.000100",
                "user": "U1",
                "text": "hello world",
                "channel": "C1",
                "permalink": "https://acme.slack.com/archives/C1/p1700000000000100",
            },
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "search", "hello", "--db", str(db_path)])
    assert rc == 0

    captured = capsys.readouterr()
    out = captured.out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    assert "Search: hello" in out
    assert "1 match(es)" in out
    assert "C1" in out
    assert "hello world" in out
    assert "acme.slack.com" in out

    err = captured.err
    assert "1 match(es)" in err
    assert "1 thread(s) (0 existing, 1 new)" in err
    assert "1 message(s) (0 existing, 1 new)" in err


def test_search_fields_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--fields selects and orders the keys emitted for each search match."""
    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(
        matches=[
            {
                "ts": "1700000000.000100",
                "user": "U1",
                "text": "hello",
                "channel": "C1",
                "permalink": "https://acme.slack.com/archives/C1/p1700000000000100",
            },
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(
        [
            "conversations",
            "search",
            "hello",
            "--json",
            "--fields",
            "text,channel,payload",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    entry = payload["matches"][0]
    assert list(entry) == ["text", "channel", "payload"]
    assert entry["text"] == "hello"
    assert entry["channel"] == "C1"
    assert entry["payload"]["permalink"].endswith("p1700000000000100")


def test_search_fields_human(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--fields restricts which parts of a match the human renderer prints."""
    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(
        matches=[
            {
                "ts": "1700000000.000100",
                "user": "U1",
                "text": "hello",
                "channel": "C1",
                "permalink": "https://acme.slack.com/archives/C1/p1700000000000100",
            },
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "search", "hello", "--fields", "text", "--db", str(db_path)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "hello" in out
    assert "[C1]" not in out
    assert "acme.slack.com" not in out


def test_search_invalid_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--fields rejects unknown search fields with a non-zero exit."""
    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(matches=[])
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "search", "hello", "--fields", "bogus", "--db", str(db_path)])
    assert rc == 2
    assert "unknown field(s): bogus" in capsys.readouterr().err


def test_search_direct_channel_hit_shows_peer_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A search hit in a direct channel is labelled with the peer's name."""
    db_path = tmp_path / "cache.db"

    class DirectSearchClient(FakeSearchClient):
        async def iter_channels(self, types="public_channel", limit=1000):
            yield {"id": "D1", "is_im": True, "user": "U1"}

        async def iter_users(self, limit: int = 1000):
            yield {"id": "U1", "name": "tomzx", "real_name": "Tom Rochette"}

    client = DirectSearchClient(
        matches=[
            {
                "ts": "1700000000.000100",
                "thread_ts": "1700000000.000100",
                "user": "U1",
                "text": "hello from the dm",
                "channel": "D1",
                "permalink": "https://acme.slack.com/archives/D1/p1700000000000100",
            },
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["channels", "fetch", "--db", str(db_path)])
    assert rc == 0
    rc = cli.main(["users", "fetch", "--db", str(db_path)])
    assert rc == 0
    rc = cli.main(["conversations", "search", "hello", "--db", str(db_path)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "[Tom Rochette (tomzx)]" in out
    assert "[D1]" not in out


def test_search_json_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Search emits JSON when --json is passed."""
    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(
        matches=[
            {
                "ts": "1700000000.000100",
                "user": "U1",
                "text": "hello",
                "channel": "C1",
                "permalink": "https://acme.slack.com/archives/C1/p1700000000000100",
            },
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "search", "hello", "--json", "--db", str(db_path)])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "hello"
    assert payload["match_count"] == 1
    assert payload["matches"][0]["text"] == "hello"
    assert payload["matches"][0]["channel"] == "C1"


def test_search_jsonl_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Search emits the whole result set as a single JSON line with --jsonl."""
    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(
        matches=[
            {
                "ts": "1700000000.000100",
                "thread_ts": "1700000000.000100",
                "user": "U1",
                "text": "hello",
                "channel": "C1",
                "permalink": "https://acme.slack.com/archives/C1/p1700000000000100",
            },
            {
                "ts": "1700000000.000200",
                "thread_ts": "1700000000.000200",
                "user": "U2",
                "text": "world",
                "channel": "C2",
                "permalink": "https://acme.slack.com/archives/C2/p1700000000000200",
            },
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "search", "hello", "--jsonl", "--db", str(db_path)])
    assert rc == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["query"] == "hello"
    assert payload["match_count"] == 2
    assert payload["matches"][0]["text"] == "hello"
    assert payload["matches"][1]["text"] == "world"


def test_search_passes_count_sort_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Search forwards --count, --sort and --sort-dir to the client."""
    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(matches=[])
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(
        [
            "conversations",
            "search",
            "deploy",
            "--count",
            "5",
            "--sort",
            "score",
            "--sort-dir",
            "asc",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0
    assert client.search_calls[0]["count"] == 5
    assert client.search_calls[0]["sort"] == "score"
    assert client.search_calls[0]["sort_dir"] == "asc"


def test_search_passes_limit_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Search forwards --limit and stops at the cap."""
    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(
        matches=[
            {"ts": f"1700000000.00010{i}", "user": "U1", "text": "hi", "channel": "C1"}
            for i in range(5)
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "search", "hi", "--limit", "2", "--db", str(db_path)])
    assert rc == 0
    assert client.search_calls[0]["limit"] == 2
    assert "2 match(es)" in capsys.readouterr().out


def test_search_defaults_limit_to_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Search applies a default limit so broad queries do not page forever."""
    from slack_cached.slack_api import DEFAULT_SEARCH_LIMIT

    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(matches=[])
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "search", "hi", "--db", str(db_path)])
    assert rc == 0
    assert client.search_calls[0]["limit"] == DEFAULT_SEARCH_LIMIT


def test_search_caches_matches_for_show(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A message found by search is afterwards retrievable via conversations show --no-fetch."""
    db_path = tmp_path / "cache.db"
    client = FakeSearchClient(
        matches=[
            {
                "ts": "1700000000.000100",
                "thread_ts": "1700000000.000100",
                "user": "U1",
                "text": "cached via search",
                "channel": "C1",
            },
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    assert cli.main(["conversations", "search", "cached", "--db", str(db_path)]) == 0
    capsys.readouterr()

    rc = cli.main(
        [
            "conversations",
            "show",
            "C1",
            "--ts",
            "1700000000.000100",
            "--db",
            str(db_path),
            "--no-fetch",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "cached via search" in out


def test_search_renders_cached_user_and_channel_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Search resolves user/channel ids to display names when cached."""
    db_path = tmp_path / "cache.db"

    class SeedClient:
        async def iter_users(self, limit: int = 1000):
            yield {"id": "U1", "name": "alice", "real_name": "Alice Smith"}

        async def iter_channels(self, types="public_channel", limit=1000):
            yield {"id": "C1", "name": "general", "is_private": False}

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: SeedClient())
    assert cli.main(["users", "fetch", "--db", str(db_path)]) == 0
    assert cli.main(["channels", "fetch", "--db", str(db_path)]) == 0
    capsys.readouterr()

    client = FakeSearchClient(
        matches=[
            {
                "ts": "1700000000.000100",
                "user": "U1",
                "text": "hello",
                "channel": "C1",
            },
        ]
    )
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda args: client)

    rc = cli.main(["conversations", "search", "hello", "--json", "--db", str(db_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["matches"][0]["user_name"] == "Alice Smith (alice)"
    assert payload["matches"][0]["channel_name"] == "general"


class FakeAsyncPollClient:
    """Async stub client for poll tests that tracks calls per channel."""

    CREDENTIALS = Creds(token="xoxb-test", cookie=None)

    def __init__(self, credentials=None, base_url=None, client=None, rate_limit_state=None):
        self._credentials = credentials or self.CREDENTIALS
        self._base_url = (base_url or "").rstrip("/")
        self._messages: dict[str, list] = {}
        self.calls: list[tuple[str, str | None]] = []
        self.rate_limit_state = rate_limit_state

    async def iter_channel_history(self, channel, oldest=None, latest=None, limit=200):
        self.calls.append((channel, oldest))
        for msg in self._messages.get(channel, []):
            yield msg

    async def iter_thread_replies(self, channel, thread_ts, oldest=None, limit=200):
        return
        yield


def _patch_poll(monkeypatch, fake_client_cls, cycle_limit=1):
    """Patch asyncio.sleep and SlackClient for poll tests.

    fake_client_cls is a class (not instance) whose __init__ accepts the
    same args as SlackClient.
    """
    import asyncio as _asyncio

    import httpx

    from slack_cached import slack_api

    monkeypatch.setattr(
        "slack_cached.config.load_credentials",
        lambda require=True: fake_client_cls.CREDENTIALS,
    )

    cycle_count = 0

    async def fake_sleep(seconds):
        nonlocal cycle_count
        cycle_count += 1
        if cycle_count >= cycle_limit:
            raise _asyncio.CancelledError()

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def close(self):
            pass

    monkeypatch.setattr(_asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())
    monkeypatch.setattr(slack_api, "SlackClient", fake_client_cls)


def test_poll_single_cycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Poll runs one cycle then stops."""
    db_path = tmp_path / "cache.db"

    class TestClient(FakeAsyncPollClient):
        def __init__(self, credentials=None, **kwargs):
            super().__init__(credentials=credentials, **kwargs)
            self._messages = {
                "C1": [{"ts": "1700000000.000100", "user": "U1", "text": "hello"}],
                "C2": [{"ts": "1700000000.000200", "user": "U2", "text": "world"}],
            }

    _patch_poll(monkeypatch, TestClient, cycle_limit=1)

    rc = cli.main(
        [
            "conversations",
            "poll",
            "--channels",
            "C1,C2",
            "--interval",
            "5m",
            "--last",
            "5m",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0

    err = capsys.readouterr().err
    assert "polling 2 channel(s)" in err
    assert "cycle 1:" in err
    assert "poll stopped after 1 cycle(s)" in err


def test_poll_json_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Poll emits JSON per cycle when --json is passed."""
    db_path = tmp_path / "cache.db"

    class TestClient(FakeAsyncPollClient):
        def __init__(self, credentials=None, **kwargs):
            super().__init__(credentials=credentials, **kwargs)
            self._messages = {
                "C1": [{"ts": "1700000000.000100", "user": "U1", "text": "msg1"}],
            }

    _patch_poll(monkeypatch, TestClient, cycle_limit=1)

    rc = cli.main(
        [
            "conversations",
            "poll",
            "--channels",
            "C1",
            "--interval",
            "5m",
            "--last",
            "5m",
            "--json",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    payload = json.loads(out.strip())
    assert payload["cycle"] == 1
    assert len(payload["channels"]) == 1
    assert payload["channels"][0]["channel"] == "C1"
    assert payload["channels"][0]["fetched"] == 1


def test_poll_multiple_cycles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Poll runs multiple cycles before stopping."""
    db_path = tmp_path / "cache.db"

    class TestClient(FakeAsyncPollClient):
        def __init__(self, credentials=None, **kwargs):
            super().__init__(credentials=credentials, **kwargs)
            self._messages = {
                "C1": [{"ts": "1700000000.000100", "user": "U1", "text": "hello"}],
            }

    _patch_poll(monkeypatch, TestClient, cycle_limit=3)

    rc = cli.main(
        [
            "conversations",
            "poll",
            "--channels",
            "C1",
            "--interval",
            "1s",
            "--last",
            "1m",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0

    err = capsys.readouterr().err
    assert "cycle 3:" in err
    assert "poll stopped after 3 cycle(s)" in err


def test_poll_requires_channels(tmp_path: Path) -> None:
    """Poll exits with error if --channels is empty."""
    db_path = tmp_path / "cache.db"
    rc = cli.main(["conversations", "poll", "--channels", "", "--db", str(db_path)])
    assert rc == 1


def test_poll_resolves_channel_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Poll resolves bare and '#'-prefixed names via the cached channels."""
    db_path = tmp_path / "cache.db"

    class ChannelsClient:
        async def iter_channels(self, types="public_channel", limit=1000):
            yield {"id": "C1", "name": "general", "is_private": False}
            yield {"id": "C2", "name": "random", "is_private": False}

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: ChannelsClient())
    assert cli.main(["channels", "fetch", "--db", str(db_path)]) == 0
    capsys.readouterr()  # clear seeding output

    class TestClient(FakeAsyncPollClient):
        def __init__(self, credentials=None, **kwargs):
            super().__init__(credentials=credentials, **kwargs)
            self._messages = {
                "C1": [{"ts": "1700000000.000100", "user": "U1", "text": "hi"}],
                "C2": [{"ts": "1700000000.000200", "user": "U2", "text": "yo"}],
                "C3": [{"ts": "1700000000.000300", "user": "U3", "text": "hey"}],
            }

    _patch_poll(monkeypatch, TestClient, cycle_limit=1)

    rc = cli.main(
        [
            "conversations",
            "poll",
            "--channels",
            "#general,random,C3",
            "--interval",
            "5m",
            "--last",
            "5m",
            "--json",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0

    payload = json.loads(capsys.readouterr().out.strip())
    polled = sorted(ch["channel"] for ch in payload["channels"])
    assert polled == ["C1", "C2", "C3"]


def test_poll_unresolved_channel_name_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Poll errors out when a channel name cannot be resolved."""
    db_path = tmp_path / "cache.db"

    class EmptyClient:
        async def iter_channels(self, types="public_channel", limit=1000):
            return
            yield  # pragma: no cover - make this an async generator

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: EmptyClient())
    _patch_poll(monkeypatch, FakeAsyncPollClient, cycle_limit=1)

    rc = cli.main(
        [
            "conversations",
            "poll",
            "--channels",
            "#nope",
            "--interval",
            "5m",
            "--last",
            "5m",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "could not resolve" in err
    assert "nope" in err


def test_poll_rejects_interval_all(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Poll rejects --interval all."""
    db_path = tmp_path / "cache.db"
    _patch_poll(monkeypatch, FakeAsyncPollClient, cycle_limit=1)

    rc = cli.main(
        [
            "conversations",
            "poll",
            "--channels",
            "C1",
            "--interval",
            "all",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 1


def test_poll_handles_channel_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Poll continues when one channel fails."""
    db_path = tmp_path / "cache.db"

    class FlakyClient(FakeAsyncPollClient):
        def __init__(self, credentials=None, **kwargs):
            super().__init__(credentials=credentials, **kwargs)
            self.ok_channel_fetched = False

        async def iter_channel_history(self, channel, oldest=None, latest=None, limit=200):
            if channel == "C_BAD":
                raise RuntimeError("api error")
            self.ok_channel_fetched = True
            yield {"ts": "1700000000.000100", "user": "U1", "text": "ok"}

    _patch_poll(monkeypatch, FlakyClient, cycle_limit=1)

    rc = cli.main(
        [
            "conversations",
            "poll",
            "--channels",
            "C_BAD,C_OK",
            "--interval",
            "5m",
            "--last",
            "5m",
            "--json",
            "--db",
            str(db_path),
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    payload = json.loads(out.strip())
    channels = payload["channels"]
    assert any("error" in ch for ch in channels)
    assert any(ch.get("fetched") == 1 for ch in channels)


def test_serve_command_is_registered(capsys: pytest.CaptureFixture[str]) -> None:
    """The serve subcommand appears in --help and accepts --host/--port."""
    rc = cli.main(["--help"])
    assert rc == 0
    assert "serve" in capsys.readouterr().out

    rc = cli.main(["serve", "--help"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "--host" in out
    assert "--port" in out


# ---------------------------------------------------------------------------
# Per-workspace cache database
# ---------------------------------------------------------------------------


def _stub_workspace_client(
    monkeypatch: pytest.MonkeyPatch,
    auth_payload: dict,
    *,
    token: str = "xoxc-test-token",
    base_url: str = "https://slack.com/api",
) -> None:
    """Stub the Slack client with a fixed auth.test identity."""

    class FakeWorkspaceClient:
        async def auth_test(self):
            return auth_payload

        async def iter_thread_replies(
            self,
            channel: str,
            thread_ts: str,
            oldest: str | None = None,
            limit: int = 200,
        ):
            yield {"ts": "1700000000.000100", "user": "U1", "text": "hello"}

        async def aclose(self) -> None:
            pass

    FakeWorkspaceClient.token = token
    FakeWorkspaceClient.base_url = base_url
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeWorkspaceClient())


def test_fetch_targets_workspace_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without --db, fetch lands in <cache>/<workspace>/threads.db via auth.test."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _stub_workspace_client(
        monkeypatch,
        {"ok": True, "url": "https://acme.slack.com/", "team_id": "TACME"},
    )

    rc = cli.main(["conversations", "fetch", "C0123ABCDEF", "--ts", "1700000000.000100"])

    assert rc == 0
    assert (tmp_path / "slackx" / "acme" / "threads.db").exists()
    assert (tmp_path / "slackx" / "last_workspace").read_text().strip() == "acme"


def test_show_reads_last_workspace_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """show --no-fetch finds the last-used workspace database without network."""

    def fail_build(common):
        raise AssertionError("show --no-fetch must not build a client")

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    _stub_workspace_client(
        monkeypatch,
        {"ok": True, "url": "https://acme.slack.com/", "team_id": "TACME"},
    )
    rc = cli.main(["conversations", "fetch", "C0123ABCDEF", "--ts", "1700000000.000100"])
    assert rc == 0

    monkeypatch.setattr(cli._internal._client, "_build_client", fail_build)
    rc = cli.main(
        [
            "conversations",
            "show",
            "C0123ABCDEF",
            "--ts",
            "1700000000.000100",
            "--no-fetch",
        ]
    )
    assert rc == 0
    assert "hello" in capsys.readouterr().out


def test_workspace_flag_selects_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--workspace names the cache directory without an auth.test call."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    class FakeWorkspaceClient:
        async def auth_test(self):
            raise AssertionError("auth.test must not run when --workspace is given")

        async def iter_thread_replies(
            self,
            channel: str,
            thread_ts: str,
            oldest: str | None = None,
            limit: int = 200,
        ):
            yield {"ts": "1700000000.000100", "user": "U1", "text": "hello"}

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: FakeWorkspaceClient())

    rc = cli.main(
        [
            "conversations",
            "fetch",
            "C0123ABCDEF",
            "--ts",
            "1700000000.000100",
            "--workspace",
            "beta",
        ]
    )

    assert rc == 0
    assert (tmp_path / "slackx" / "beta" / "threads.db").exists()
    assert (tmp_path / "slackx" / "last_workspace").read_text().strip() == "beta"


def test_show_requires_workspace_when_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Multiple workspace caches without a last-used pointer is an error."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    from slack_cached.storage import connect
    from slack_cached.workspace import workspace_db_path

    connect(workspace_db_path("alpha")).close()
    connect(workspace_db_path("beta")).close()

    with pytest.raises(SystemExit, match="alpha, beta"):
        cli.main(
            [
                "conversations",
                "show",
                "C0123ABCDEF",
                "--ts",
                "1700000000.000100",
                "--no-fetch",
            ]
        )


def test_auth_test_runs_once_per_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The first fetch resolves via auth.test; later fetches reuse the disk cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    auth_calls: list[int] = []
    payload = {"ok": True, "url": "https://acme.slack.com/", "team_id": "TACME"}

    class CountingClient:
        token = "xoxc-test-token"
        base_url = "https://slack.com/api"

        async def auth_test(self):
            auth_calls.append(1)
            return payload

        async def iter_thread_replies(self, channel, thread_ts, oldest=None, limit=200):
            yield {"ts": "1700000000.000100", "user": "U1", "text": "hello"}

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: CountingClient())

    for _ in range(2):
        rc = cli.main(["conversations", "fetch", "C0123ABCDEF", "--ts", "1700000000.000100"])
        assert rc == 0

    assert len(auth_calls) == 1
    names = json.loads((tmp_path / "slackx" / "workspace_names.json").read_text())
    assert len(names) == 1
    assert "acme" in names.values()


def test_serve_sync_resolution_uses_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without --db/--workspace, serve resolves the workspace from credentials."""
    from slack_cached.cli._internal import _client
    from slack_cached.cli._internal._shared import CommonArgs
    from slack_cached.workspace import workspace_db_path

    common = CommonArgs()
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("SLACK_TOKEN", "xoxc-test-token")
    monkeypatch.setenv("SLACK_COOKIE", "xoxd-test-cookie")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Cache miss: auth.test runs via the (stubbed) client, then is stored.
    _stub_workspace_client(
        monkeypatch,
        {"ok": True, "url": "https://acme.slack.com/", "team_id": "TACME"},
    )
    assert _client._resolve_db_path_sync(common) == workspace_db_path("acme")

    # Cache hit: no client is built and no network call is made.
    def fail_build(common):
        raise AssertionError("cached workspace must not build a client")

    monkeypatch.setattr(cli._internal._client, "_build_client", fail_build)
    assert _client._resolve_db_path_sync(common) == workspace_db_path("acme")


def test_serve_sync_resolution_without_credentials_falls_back_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No credentials: serve falls back to offline resolution."""
    from slack_cached.cli._internal import _client
    from slack_cached.cli._internal._shared import CommonArgs
    from slack_cached.workspace import offline_db_path

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.delenv("SLACK_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    common = CommonArgs()
    assert _client._resolve_db_path_sync(common) == offline_db_path()


def _seed_all_entities(db_path: Path) -> None:
    """Cache one thread/message, one user, and one channel directly."""
    from slack_cached.storage import (
        connect,
        record_thread_refresh,
        upsert_channels,
        upsert_messages,
        upsert_users,
    )

    conn = connect(db_path)
    try:
        with conn:
            record_thread_refresh(conn, "C1", "1700000000.000100", None)
            upsert_messages(
                conn,
                "C1",
                "1700000000.000100",
                [{"ts": "1700000000.000100", "user": "U1", "text": "hello"}],
            )
            upsert_users(conn, [{"id": "U1", "name": "alice", "real_name": "Alice Smith"}])
            upsert_channels(conn, [{"id": "C1", "name": "general", "is_private": False}])
    finally:
        conn.close()


def _status_counts(db_path: Path):
    from slack_cached.storage import connect, db_status

    conn = connect(db_path)
    try:
        return db_status(conn)
    finally:
        conn.close()


def test_clear_requires_confirmation_without_yes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --yes (and no interactive stdin) clear refuses and deletes nothing."""
    db_path = tmp_path / "cache.db"
    _seed_all_entities(db_path)

    rc = cli.main(["cache", "clear", "--db", str(db_path)])

    assert rc == 1
    assert "pass --yes" in capsys.readouterr().err
    counts = _status_counts(db_path)
    assert counts.message_count == 1
    assert counts.thread_count == 1
    assert counts.channel_count == 1
    assert counts.user_count == 1


def test_clear_defaults_to_everything(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """clear with no target removes messages, threads, channels, and users."""
    db_path = tmp_path / "cache.db"
    _seed_all_entities(db_path)

    rc = cli.main(["cache", "clear", "--yes", "--db", str(db_path)])

    assert rc == 0
    assert "messages=1 threads=1 channels=1 users=1" in capsys.readouterr().err
    counts = _status_counts(db_path)
    assert counts.message_count == 0
    assert counts.thread_count == 0
    assert counts.channel_count == 0
    assert counts.user_count == 0


def test_clear_messages_also_clears_threads_and_keeps_the_rest(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "cache.db"
    _seed_all_entities(db_path)

    rc = cli.main(["cache", "clear", "messages", "--yes", "--db", str(db_path)])

    assert rc == 0
    counts = _status_counts(db_path)
    assert counts.message_count == 0
    assert counts.thread_count == 0
    assert counts.channel_count == 1
    assert counts.user_count == 1


def test_clear_channels_keeps_messages_and_users(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    _seed_all_entities(db_path)

    rc = cli.main(["cache", "clear", "channels", "--yes", "--db", str(db_path)])

    assert rc == 0
    counts = _status_counts(db_path)
    assert counts.channel_count == 0
    assert counts.message_count == 1
    assert counts.thread_count == 1
    assert counts.user_count == 1


def test_clear_users_keeps_messages_and_channels(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    _seed_all_entities(db_path)

    rc = cli.main(["cache", "clear", "users", "--yes", "--db", str(db_path)])

    assert rc == 0
    counts = _status_counts(db_path)
    assert counts.user_count == 0
    assert counts.message_count == 1
    assert counts.thread_count == 1
    assert counts.channel_count == 1


def test_clear_messages_reopens_thread_for_refetch(tmp_path: Path) -> None:
    """Clearing messages drops the thread row so show refetches instead of trusting it."""
    from slack_cached.storage import connect, get_thread_state

    db_path = tmp_path / "cache.db"
    _seed_all_entities(db_path)

    assert cli.main(["cache", "clear", "messages", "--yes", "--db", str(db_path)]) == 0

    conn = connect(db_path)
    try:
        assert get_thread_state(conn, "C1", "1700000000.000100") is None
    finally:
        conn.close()
