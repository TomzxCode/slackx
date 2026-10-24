"""Tests for the JSON-RPC API, client, and CLI commands."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import structlog
from fastapi.testclient import TestClient

from slackx import cache, cli, storage
from slackx.rpc import client as rpc_client
from slackx.rpc import methods as rpc_methods
from slackx.rpc.protocol import RpcError
from slackx.server import app as server_app


@pytest.fixture(autouse=True)
def _silence_logging() -> Iterator[None]:
    """Keep structlog away from pytest's capture files.

    ``cli.main`` configures structlog with the current ``sys.stderr``. Pytest
    closes that capture file after the test, so leaving that configuration in
    place makes every later log call fail. Restore a file-free configuration
    before and after each test instead.
    """

    def configure() -> None:
        structlog.configure(
            processors=[],
            wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
            logger_factory=structlog.ReturnLoggerFactory(),
        )

    configure()
    yield
    configure()


class _NoopSlackClient:
    """Clients are built but never called when a fetch itself is stubbed."""

    async def aclose(self) -> None:
        return None


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "cache.db"


def _populate(db: Path) -> None:
    conn = storage.connect(db)
    try:
        storage.upsert_users(
            conn,
            [
                {"id": "U1", "name": "alice", "real_name": "Alice Smith"},
                {"id": "U2", "name": "bob", "real_name": "Bob Jones"},
            ],
        )
        storage.upsert_channels(conn, [{"id": "C1", "name": "general", "is_private": False}])
        storage.record_thread_refresh(conn, "C1", "1700000000.000001", "1700000000.000002")
        storage.upsert_messages(
            conn,
            "C1",
            "1700000000.000001",
            [
                {"ts": "1700000000.000001", "user": "U1", "text": "hello world"},
                {"ts": "1700000000.000002", "user": "U2", "text": "a reply"},
            ],
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def client(db_path: Path) -> TestClient:
    _populate(db_path)
    with TestClient(server_app.create_app(db_path=db_path)) as test_client:
        yield test_client


def _rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post(
        "/rpc",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )
    assert response.status_code == 200
    return response.json()


def test_system_methods(client: TestClient) -> None:
    body = _rpc(client, "system.methods")
    names = {entry["name"] for entry in body["result"]["methods"]}
    assert {
        "cache.status",
        "conversations.get",
        "conversations.fetch",
        "conversations.search",
        "users.list",
        "users.get",
        "channels.list",
        "channels.get",
        "read.mark",
        "read.show",
        "read.clear",
    } <= names


def test_users_list_uses_cache(client: TestClient) -> None:
    body = _rpc(client, "users.list", {"fetch": False})
    assert body["result"]["user_count"] == 2
    assert body["result"]["users"][0] == {
        "id": "U1",
        "name": "alice",
        "real_name": "Alice Smith",
    }


def test_users_get_and_fields(client: TestClient) -> None:
    body = _rpc(client, "users.get", {"user": "U1", "fetch": False, "fields": ["id", "name"]})
    assert body["result"] == {"user_count": 1, "users": [{"id": "U1", "name": "alice"}]}


def test_users_get_missing_is_server_error(client: TestClient) -> None:
    body = _rpc(client, "users.get", {"user": "U404", "fetch": False})
    assert body["error"]["code"] == -32000
    assert "not cached" in body["error"]["message"]


def test_channels_list_uses_cache(client: TestClient) -> None:
    body = _rpc(client, "channels.list", {"fetch": False})
    assert body["result"]["channel_count"] == 1
    assert body["result"]["channels"] == [{"id": "C1", "name": "general", "is_private": False}]


def test_channels_get_uses_cache(client: TestClient) -> None:
    body = _rpc(client, "channels.get", {"channel": "C1", "fetch": False})
    assert body["result"] == {
        "channel_count": 1,
        "channels": [{"id": "C1", "name": "general", "is_private": False}],
    }


def test_channels_get_resolves_cached_name(client: TestClient) -> None:
    body = _rpc(client, "channels.get", {"channel": "general", "fetch": False})
    assert body["result"]["channels"][0]["id"] == "C1"


def test_channels_get_missing_is_server_error(client: TestClient) -> None:
    body = _rpc(client, "channels.get", {"channel": "C404", "fetch": False})
    assert body["error"]["code"] == -32000
    assert "not cached" in body["error"]["message"]


def test_conversations_get_channel(client: TestClient) -> None:
    body = _rpc(
        client,
        "conversations.get",
        {"target": "C1", "fetch": False, "last": "all", "reader": None},
    )
    result = body["result"]
    assert result["channel"] == "C1"
    assert result["channel_name"] == "general"
    assert result["message_count"] == 1
    assert result["messages"][0]["text"] == "hello world"
    assert result["messages"][0]["user_name"] == "Alice Smith (alice)"


def test_conversations_get_thread(client: TestClient) -> None:
    body = _rpc(
        client,
        "conversations.get",
        {"target": "C1", "ts": "1700000000.000001", "fetch": False, "reader": None},
    )
    result = body["result"]
    assert result["thread_ts"] == "1700000000.000001"
    assert result["message_count"] == 2
    assert [m["text"] for m in result["messages"]] == ["hello world", "a reply"]


def test_conversations_get_advances_read_marker(client: TestClient) -> None:
    body = _rpc(
        client,
        "conversations.get",
        {"target": "C1", "fetch": False, "reader": "web"},
    )
    assert "error" not in body

    shown = _rpc(client, "read.show", {"reader": "web"})
    markers = shown["result"]["markers"]
    assert len(markers) == 1
    assert markers[0]["last_read_ts"] == "1700000000.000002"


def test_conversations_get_null_reader_does_not_mark(client: TestClient) -> None:
    body = _rpc(
        client,
        "conversations.get",
        {"target": "C1", "fetch": False, "reader": None},
    )
    assert "error" not in body
    shown = _rpc(client, "read.show", {})
    assert shown["result"]["read_count"] == 0


def test_conversations_get_channel_last_filters_display(client: TestClient, db_path: Path) -> None:
    """conversations.get hides cached rows outside the requested lookback."""
    now = time.time()
    old_ts = f"{now - 400 * 86400:.6f}"
    recent_ts = f"{now - 60:.6f}"
    conn = storage.connect(db_path)
    try:
        storage.record_thread_refresh(conn, "C2", old_ts, None)
        storage.upsert_messages(
            conn, "C2", old_ts, [{"ts": old_ts, "user": "U1", "text": "from-2025"}]
        )
        storage.record_thread_refresh(conn, "C2", recent_ts, None)
        storage.upsert_messages(
            conn, "C2", recent_ts, [{"ts": recent_ts, "user": "U1", "text": "from-today"}]
        )
        conn.commit()
    finally:
        conn.close()

    def shown(last: str) -> list[str]:
        body = _rpc(
            client,
            "conversations.get",
            {"target": "C2", "fetch": False, "last": last, "reader": None},
        )
        return [m["text"] for m in body["result"]["messages"]]

    assert shown("1d") == ["from-today"]
    assert shown("all") == ["from-2025", "from-today"]


def test_conversations_get_unknown_id_returns_empty(client: TestClient) -> None:
    # A channel id is accepted as-is, matching the CLI; nothing cached means
    # an empty message list rather than an error.
    body = _rpc(client, "conversations.get", {"target": "C404", "fetch": False})
    assert body["result"]["channel"] == "C404"
    assert body["result"]["messages"] == []


def test_conversations_fetch_thread(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_fetch_thread(
        conn: object, slack_client: object, ref: object
    ) -> cache.FetchResult:
        calls.append((ref.channel, ref.thread_ts))
        return cache.FetchResult(
            channel=ref.channel,
            thread_ts=ref.thread_ts,
            fetched_messages=2,
            total_messages=2,
            incremental=False,
        )

    monkeypatch.setattr(cache, "fetch_thread", fake_fetch_thread)
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: _NoopSlackClient())

    body = _rpc(
        client,
        "conversations.fetch",
        {"target": "C1", "ts": "1700000000.000001"},
    )
    assert body["result"] == {
        "kind": "thread",
        "channel": "C1",
        "thread_ts": "1700000000.000001",
        "fetched_messages": 2,
        "total_messages": 2,
        "incremental": False,
    }
    assert calls == [("C1", "1700000000.000001")]


def test_conversations_fetch_channel(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool, str | None]] = []

    async def fake_fetch_channel(
        conn: object,
        slack_client: object,
        channel: str,
        *,
        full_threads: bool = False,
        oldest: str | None = None,
    ) -> cache.ChannelFetchResult:
        calls.append((channel, full_threads, oldest))
        return cache.ChannelFetchResult(
            channel=channel,
            fetched_messages=3,
            total_messages=4,
            threads_with_replies_fetched=1,
        )

    monkeypatch.setattr(cache, "fetch_channel_messages", fake_fetch_channel)
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: _NoopSlackClient())

    body = _rpc(client, "conversations.fetch", {"target": "C1", "full_threads": True})
    assert body["result"]["kind"] == "channel"
    assert body["result"]["fetched_messages"] == 3
    assert body["result"]["threads_with_replies_fetched"] == 1
    assert len(calls) == 1
    channel, full_threads, oldest = calls[0]
    assert (channel, full_threads) == ("C1", True)
    assert oldest is not None


def test_conversations_search(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_search(
        conn: object,
        slack_client: object,
        *,
        query: str,
        count: int,
        sort: str,
        sort_dir: str,
        full_threads: bool,
        limit: int,
    ) -> cache.SearchFetchResult:
        assert query == "hello"
        assert count == 20
        return cache.SearchFetchResult(
            query=query,
            matches=[
                {
                    "channel": "C1",
                    "ts": "1700000000.000001",
                    "user": "U1",
                    "text": "hello world",
                    "permalink": "https://example.slack.com/archives/C1/p1700000000000001",
                }
            ],
            threads_seen=1,
            threads_new=1,
            messages_seen=1,
            messages_new=1,
        )

    monkeypatch.setattr(cache, "fetch_search", fake_fetch_search)
    monkeypatch.setattr(cli._internal._client, "_build_client", lambda _: _NoopSlackClient())

    body = _rpc(client, "conversations.search", {"query": "hello"})
    result = body["result"]
    assert result["match_count"] == 1
    assert result["matches"][0]["text"] == "hello world"
    assert result["matches"][0]["user_name"] == "Alice Smith (alice)"
    assert result["matches"][0]["channel_name"] == "general"
    assert result["stats"] == {
        "threads_seen": 1,
        "threads_new": 1,
        "messages_seen": 1,
        "messages_new": 1,
    }


def test_read_mark_and_clear(client: TestClient) -> None:
    marked = _rpc(
        client,
        "read.mark",
        {"target": "C1", "ts": "1700000000.000001", "reader": "web"},
    )
    assert marked["result"]["marker"]["last_read_ts"] == "1700000000.000002"

    cleared = _rpc(client, "read.clear", {"reader": "web", "channel": "C1"})
    assert cleared["result"]["deleted"] == 1

    shown = _rpc(client, "read.show", {"reader": "web"})
    assert shown["result"]["read_count"] == 0


def test_read_clear_requires_channel_for_ts(client: TestClient) -> None:
    body = _rpc(client, "read.clear", {"reader": "web", "ts": "1.0"})
    assert body["error"]["code"] == -32602


def test_cache_status(client: TestClient) -> None:
    body = _rpc(client, "cache.status")
    result = body["result"]
    assert result["channel_count"] == 1
    assert result["user_count"] == 2
    assert result["message_count"] == 2
    assert result["db_path"].endswith(".db")


def test_cache_clear_target(client: TestClient) -> None:
    body = _rpc(client, "cache.clear", {"target": "users"})
    assert body["result"]["users"] == 2
    status = _rpc(client, "cache.status")["result"]
    assert status["user_count"] == 0
    assert status["channel_count"] == 1


def test_unknown_method(client: TestClient) -> None:
    body = _rpc(client, "does.not.exist")
    assert body["error"]["code"] == -32601


def test_unknown_parameter_is_invalid_params(client: TestClient) -> None:
    body = _rpc(client, "users.list", {"nope": True})
    assert body["error"]["code"] == -32602
    assert "nope" in body["error"]["message"]


def test_database_and_api_base_are_not_client_settable(client: TestClient) -> None:
    for params in ({"db_path": "/tmp/other.db"}, {"api_base_url": "http://evil"}):
        body = _rpc(client, "cache.status", params)
        assert body["error"]["code"] == -32602


def test_unexpected_exception_hides_traceback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(_ctx: object, _params: dict[str, Any]) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setitem(
        rpc_methods._METHODS,
        "cache.status",
        rpc_methods.Method("cache.status", "test", (), boom),
    )
    body = _rpc(client, "cache.status")
    assert body["error"]["code"] == -32000
    assert body["error"]["message"] == "RuntimeError: kaboom"
    assert "Traceback" not in json.dumps(body)


def test_wrong_parameter_type_is_invalid_params(client: TestClient) -> None:
    body = _rpc(client, "users.list", {"limit": "ten"})
    assert body["error"]["code"] == -32602


def test_missing_required_parameter(client: TestClient) -> None:
    body = _rpc(client, "users.get", {})
    assert body["error"]["code"] == -32602


def test_invalid_request_object(client: TestClient) -> None:
    response = client.post("/rpc", json={"id": 1, "method": "system.methods"})
    assert response.json()["error"]["code"] == -32600


def test_parse_error(client: TestClient) -> None:
    response = client.post("/rpc", content=b"{not json")
    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32700


def test_notification_returns_no_content(client: TestClient) -> None:
    response = client.post(
        "/rpc", json={"jsonrpc": "2.0", "method": "users.list", "params": {"fetch": False}}
    )
    assert response.status_code == 204
    assert response.content == b""


def test_batch_mixes_results_and_errors(client: TestClient) -> None:
    response = client.post(
        "/rpc",
        json=[
            {"jsonrpc": "2.0", "id": 1, "method": "cache.status"},
            {"jsonrpc": "2.0", "id": 2, "method": "does.not.exist"},
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == 1
    assert "result" in body[0]
    assert body[1]["error"]["code"] == -32601


def test_empty_batch_is_invalid_request(client: TestClient) -> None:
    response = client.post("/rpc", json=[])
    assert response.json()["error"]["code"] == -32600


def test_client_call_and_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["method"] == "fail":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "error": {"code": -32000, "message": "boom"},
                },
            )
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": {"ok": True}},
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = rpc_client.RpcClient("http://test/rpc", client=http_client)
            assert await client.call("users.list") == {"ok": True}
            with pytest.raises(RpcError) as excinfo:
                await client.call("fail")
            assert excinfo.value.code == -32000

    import asyncio

    asyncio.run(run())


def test_client_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = rpc_client.RpcClient("http://test/rpc", client=http_client)
            with pytest.raises(rpc_client.RpcTransportError):
                await client.call("users.list")

    import asyncio

    asyncio.run(run())


def test_rpc_and_cli_json_payloads_match(db_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _populate(db_path)
    with TestClient(server_app.create_app(db_path=db_path)) as test_client:
        rpc_payload = _rpc(
            test_client,
            "conversations.get",
            {"target": "C1", "ts": "1700000000.000001", "fetch": False, "reader": None},
        )["result"]

    rc = cli.main(
        [
            "conversations",
            "get",
            "C1",
            "--ts",
            "1700000000.000001",
            "--db",
            str(db_path),
            "--no-fetch",
            "--json",
        ]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == rpc_payload


class _FakeCliClient:
    """Stand-in for RpcClient used by the ``rpc`` command tests."""

    calls: list[tuple[str, dict[str, Any]]] = []
    result: Any = {"ok": True}
    error: RpcError | None = None
    exec_calls: list[tuple[list[str], str]] = []
    exec_result: dict[str, Any] = {"stdout": "", "stderr": "", "exitCode": 0}

    def __init__(self, _url: str, token: str | None = None) -> None:
        self.token = token

    async def __aenter__(self) -> _FakeCliClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, params or {}))
        if self.error is not None:
            raise self.error
        return self.result

    async def methods(self) -> list[dict[str, Any]]:
        return [{"name": "users.list", "description": "List users.", "params": ["limit"]}]

    async def exec(self, args: list[str], stdin: str = "") -> dict[str, Any]:
        self.exec_calls.append((args, stdin))
        return self.exec_result


def test_rpc_methods_lists_catalog(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rpc_client, "RpcClient", _FakeCliClient)

    rc = cli.main(["rpc", "methods", "--url", "http://x/rpc"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "users.list" in out
    assert "List users." in out


def test_rpc_methods_prints_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(rpc_client, "RpcClient", _FakeCliClient)

    rc = cli.main(["rpc", "methods", "--url", "http://x/rpc", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == [
        {"name": "users.list", "description": "List users.", "params": ["limit"]}
    ]


def test_rpc_call_prints_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _FakeCliClient.calls = []
    _FakeCliClient.result = {"user_count": 0, "users": []}
    _FakeCliClient.error = None
    monkeypatch.setattr(rpc_client, "RpcClient", _FakeCliClient)

    rc = cli.main(
        ["rpc", "call", "users.list", "--params", '{"fetch": false}', "--url", "http://x/rpc"]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"user_count": 0, "users": []}
    assert _FakeCliClient.calls == [("users.list", {"fetch": False})]


def test_rpc_call_reports_rpc_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _FakeCliClient.error = RpcError(-32000, "boom")
    monkeypatch.setattr(rpc_client, "RpcClient", _FakeCliClient)

    try:
        rc = cli.main(["rpc", "call", "users.list", "--url", "http://x/rpc"])
    finally:
        _FakeCliClient.error = None
    assert rc == 1
    assert "boom" in capsys.readouterr().err


def test_rpc_call_rejects_invalid_params_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["rpc", "call", "users.list", "--params", "[1, 2]"])
    assert rc == 2
    assert "JSON object" in capsys.readouterr().err


def test_rpc_discover_lists_server_and_methods(client: TestClient) -> None:
    body = _rpc(client, "rpc.discover")
    result = body["result"]
    assert result["name"] == "slackx"
    assert result["version"]
    names = {entry["name"] for entry in result["methods"]}
    assert {"rpc.discover", "server.info", "cli.run", "users.list"} <= names


def test_system_methods_remains_an_alias(client: TestClient) -> None:
    body = _rpc(client, "system.methods")
    names = {entry["name"] for entry in body["result"]["methods"]}
    assert "rpc.discover" in names
    assert "users.list" in names


def test_server_info(client: TestClient, db_path: Path) -> None:
    result = _rpc(client, "server.info")["result"]
    assert result["name"] == "slackx"
    assert result["dbPath"] == str(db_path)
    assert result["execEnabled"] is True
    assert result["startedAt"]


def test_cli_run_executes_a_command(client: TestClient, db_path: Path) -> None:
    result = _rpc(client, "cli.run", {"args": ["cache", "status", "--json"]})["result"]
    assert result["exitCode"] == 0
    assert result["stderr"] == ""
    assert json.loads(result["stdout"])["db_path"] == str(db_path)


def test_cli_run_is_hidden_and_rejected_when_disabled(db_path: Path) -> None:
    with TestClient(server_app.create_app(db_path=db_path, rpc_allow_exec=False)) as test_client:
        names = {entry["name"] for entry in _rpc(test_client, "rpc.discover")["result"]["methods"]}
        assert "cli.run" not in names
        body = _rpc(test_client, "cli.run", {"args": ["cache", "status"]})
        assert body["error"]["code"] == -32601


def test_rpc_requires_a_bearer_token(db_path: Path) -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "server.info"}
    with TestClient(server_app.create_app(db_path=db_path, rpc_token="secret")) as test_client:
        assert test_client.post("/rpc", json=payload).status_code == 401
        wrong = test_client.post("/rpc", json=payload, headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401
        allowed = test_client.post("/rpc", json=payload, headers={"Authorization": "Bearer secret"})
        assert allowed.status_code == 200
        header_token = test_client.post("/rpc", json=payload, headers={"X-Slackx-Token": "secret"})
        assert header_token.status_code == 200


def test_rpc_call_accepts_positional_params(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _FakeCliClient.calls = []
    _FakeCliClient.result = {"ok": True}
    _FakeCliClient.error = None
    monkeypatch.setattr(rpc_client, "RpcClient", _FakeCliClient)

    rc = cli.main(["rpc", "call", "users.list", '{"fetch": false}', "--url", "http://x/rpc"])
    assert rc == 0
    assert _FakeCliClient.calls == [("users.list", {"fetch": False})]
    assert json.loads(capsys.readouterr().out) == {"ok": True}


def test_remote_forwards_to_cli_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _FakeCliClient.exec_calls = []
    _FakeCliClient.exec_result = {"stdout": "hello\n", "stderr": "warning\n", "exitCode": 3}
    monkeypatch.setattr(rpc_client, "RpcClient", _FakeCliClient)

    rc = cli.main(["--remote", "http://x", "conversations", "get", "C1"])
    assert rc == 3
    assert _FakeCliClient.exec_calls == [(["conversations", "get", "C1"], "")]
    captured = capsys.readouterr()
    assert captured.out == "hello\n"
    assert captured.err == "warning\n"


def test_rpc_exec_forwards_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _FakeCliClient.exec_calls = []
    _FakeCliClient.exec_result = {"stdout": "ok\n", "stderr": "", "exitCode": 0}
    monkeypatch.setattr(rpc_client, "RpcClient", _FakeCliClient)

    rc = cli.main(["rpc", "exec", "--url", "http://x", "--", "cache", "status", "--json"])
    assert rc == 0
    assert _FakeCliClient.exec_calls == [(["cache", "status", "--json"], "")]
    assert capsys.readouterr().out == "ok\n"
