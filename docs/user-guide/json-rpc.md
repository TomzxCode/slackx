# JSON-RPC API

The `slackx` CLI can also run as a JSON-RPC 2.0 server.
Clients call methods on that server instead of spawning a CLI command for every operation.
This keeps one process holding the cache warm and gives programs a typed, JSON-native surface.

The server is the same FastAPI app used by the web UI, so `slackx serve` exposes both.
`slackx rpc serve` starts the same app when only the API matters.

## Start the server

```bash
slackx rpc serve --db ~/.cache/slackx/acme/threads.db --port 8280
```

The JSON-RPC endpoint is `POST http://127.0.0.1:8280/rpc`.
Without `--db` or `--workspace`, the workspace is resolved from the configured token, exactly like the CLI.

## Call a method

```bash
slackx rpc methods
slackx rpc call users.list --params '{"limit": 20}'
slackx rpc call conversations.get --params '{"target": "#general", "fetch": false}'
```

`slackx rpc call` prints the JSON result to stdout.
JSON-RPC errors go to stderr and the command exits non-zero.

The endpoint defaults to `http://127.0.0.1:8280/rpc`.
Override it per call with `--url` (or `--server`), or globally with `SLACKX_RPC_URL`:

```bash
SLACKX_RPC_URL=http://127.0.0.1:9000/rpc slackx rpc methods
slackx rpc call cache.status --url http://127.0.0.1:9000/rpc
```

Parameters can come from a file, or from stdin with `-`:

```bash
slackx rpc call conversations.search --params-file search.json
echo '{"limit": 5}' | slackx rpc call users.list --params-file -
```

## Protocol

The endpoint implements JSON-RPC 2.0.
It accepts one request object or a batch (a JSON array).
A request without an `id` is a notification and gets HTTP 204 with no body.
Request-level failures return HTTP 200 with an `error` object, as the specification requires.

```bash
curl -s http://127.0.0.1:8280/rpc \
  -H 'content-type: application/json' \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "cache.status"}'
```

```json
{"jsonrpc": "2.0", "id": 1, "result": {"workspace": "acme", "db_path": "...", "message_count": 42}}
```

Application failures use the implementation-defined code `-32000`.
The reserved codes are `-32700` (parse error), `-32600` (invalid request), `-32601` (method not found), and `-32602` (invalid params).

Every method rejects unknown parameters, so a typo is an error instead of a silently ignored option.

## Methods

Results match the CLI's `--json` payloads where a command has a JSON form.
The server's database and API base URL are fixed at startup; a client cannot select another workspace.
Slack credentials come from the server process's environment or config file.

| Method | Parameters | Result |
|---|---|---|
| `system.methods` | none | `{"methods": [{"name", "description", "params"}]}` |
| `cache.status` | none | Status payload: workspace, db_path, and `DbStatus` counts |
| `cache.clear` | `target` (`all`, `messages`, `channels`, `users`, `read`) | `ClearedCounts` |
| `users.list` | `limit`, `fields`, `fetch` | `{"user_count", "users"}` |
| `users.get` | `user`, `fields`, `fetch` | `{"user_count", "users"}` with one user |
| `channels.list` | `limit`, `fields`, `fetch` | `{"channel_count", "channels"}` |
| `channels.get` | `channel`, `fields`, `fetch` | `{"channel_count", "channels"}` with one channel |
| `conversations.fetch` | `target`, `ts`, `full_threads`, `last` | `{"kind": "thread"\|"channel", ...fetch counts}` |
| `conversations.get` | `target`, `ts`, `fetch`, `with_thread_message`, `last`, `reader` | Thread or channel message payload |
| `conversations.search` | `query`, `count`, `limit`, `sort`, `sort_dir`, `full_threads`, `fields` | `{"query", "match_count", "matches", "stats"}` |
| `read.mark` | `target`, `ts`, `reader`, `last_read` | `{"marker": {...}}` |
| `read.show` | `reader`, `channel` | `{"read_count", "markers"}` |
| `read.clear` | `reader`, `channel`, `ts` | `{"deleted": n}` |

Notes on parity with the CLI:

- `fetch` defaults to auto-fetch on a cache miss, the same as the CLI.
  Pass `false` to stay offline; `conversations.get` also accepts `null` for the CLI default.
- `conversations.get` advances the `reader` pointer to the newest cached message, the same as the CLI.
  Pass `"reader": null` to skip that.
- `cache.clear` never prompts. The caller is explicit and the RPC call is the confirmation.
- `conversations.poll`, `serve`, and the fake Slack server are not RPC methods: they are long-running processes, not request/response operations.
- `target` accepts a Slack permalink, a channel id, a channel name (`general` or `#general`), or a user id or `@handle` for that direct message.

## Python client

```python
import asyncio

from slackx.rpc.client import RpcClient


async def main() -> None:
    async with RpcClient("http://127.0.0.1:8280/rpc") as client:
        status = await client.call("cache.status")
        users = await client.call("users.list", {"limit": 20})
        print(status["message_count"], users["user_count"])


asyncio.run(main())
```

The client raises `slackx.rpc.protocol.RpcError` for JSON-RPC errors and `slackx.rpc.client.RpcTransportError` when the server cannot be reached.
