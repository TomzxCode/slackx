# JSON-RPC API

The `slackx` CLI can also run as a JSON-RPC 2.0 server.
Clients call methods on that server instead of spawning a CLI command for every operation.
This keeps one process holding the cache warm and gives programs a typed, JSON-native surface.

The server is the same FastAPI app used by the web UI, so `slackx serve` exposes both.
`slackx rpc serve` starts the same app when only the API matters.

## Start the server

```bash
slackx rpc serve --db ~/.cache/slackx/acme/threads.db --host 127.0.0.1 --port 8280
```

The JSON-RPC endpoint is `POST http://127.0.0.1:8280/rpc`.
Without `--db` or `--workspace`, the workspace is resolved from the configured token, exactly like the CLI.

The same options work on `slackx serve`, which also serves the web UI.

Binding a non-loopback host requires a token, because clients can change the cache and run CLI commands:

```bash
slackx rpc serve --host 0.0.0.0 --port 8280 --token "$SLACKX_RPC_TOKEN"
slackx serve --host 0.0.0.0 --port 8280 --rpc-token "$SLACKX_RPC_TOKEN"
```

Command execution is on by default.
Disable it with `--no-allow-exec` on `rpc serve` or `--no-rpc-allow-exec` on `serve`, which removes `cli.run` from the method catalog.

## Call a method

```bash
slackx rpc methods
slackx rpc call users.list '{"limit": 20}'
slackx rpc call conversations.get '{"target": "#general", "fetch": false}'
```

The second argument is a JSON object.
Use `-` to read it from stdin or `@path` to read it from a file.
The older `--params` and `--params-file` flags still work.

`slackx rpc call` prints the JSON result to stdout.
JSON-RPC errors go to stderr and the command exits non-zero.
Use `--compact` to print the result as one line.

The endpoint defaults to `http://127.0.0.1:8280/rpc`.
Override it per call with `--url` (or `--server`), or globally with `SLACKX_RPC_URL`:

```bash
SLACKX_RPC_URL=http://127.0.0.1:9000/rpc slackx rpc methods
slackx rpc call cache.status --url http://127.0.0.1:9000/rpc
```

## Run any CLI command

The `cli.run` method executes a `slackx` command on the server and returns its captured output and exit code:

```bash
slackx rpc call cli.run '{"args": ["cache", "status", "--json"]}'
```

Output shape:

```json
{"stdout": "...", "stderr": "", "exitCode": 0}
```

`slackx rpc exec` is a convenient wrapper:

```bash
slackx rpc exec -- conversations search "deploy" --json
slackx rpc exec -- conversations get C1 --json
```

Put the remote command after `--` so its own flags are not parsed by `rpc exec`.
Leading `--url` and `--token` options select the server:

```bash
slackx rpc exec --url http://127.0.0.1:9000 -- conversations get C1
```

## Transparent remote mode

Prepend `--remote` to any command to run it on a server instead of locally:

```bash
slackx --remote http://127.0.0.1:8280 conversations get C1 --json
slackx --remote --rpc-token "$SLACKX_RPC_TOKEN" conversations search "deploy"
```

Output and the exit status are forwarded, so scripts behave the same way.
Piped stdin is forwarded too, so commands that read it work through the server.
The URL can come from `SLACKX_RPC_URL` and the token from `SLACKX_RPC_TOKEN`.

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
| `rpc.discover` | none | `{"name", "version", "methods": [{"name", "description", "params"}]}` |
| `system.methods` | none | Alias of `rpc.discover`; returns `{"methods": [...]}` |
| `server.info` | none | Server name, version, workspace, database path, `execEnabled`, method count, and start time |
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
| `cli.run` | `args`, `stdin` | `{"stdout", "stderr", "exitCode"}` |

Notes on parity with the CLI:

- `fetch` defaults to auto-fetch on a cache miss, the same as the CLI.
  Pass `false` to stay offline; `conversations.get` also accepts `null` for the CLI default.
- `conversations.get` advances the `reader` pointer to the newest cached message, the same as the CLI.
  Pass `"reader": null` to skip that.
- `cache.clear` never prompts. The caller is explicit and the RPC call is the confirmation.
- `conversations.poll`, `serve`, and the fake Slack server are not RPC methods: they are long-running processes, not request/response operations.
- `target` accepts a Slack permalink, a channel id, a channel name (`general` or `#general`), or a user id or `@handle` for that direct message.
- `cli.run` appends the server's database path, API base URL, and log level to the forwarded command, so the child uses the same cache and Slack target.

## Authentication and security

The server binds to loopback by default.

When `--token` (or `--rpc-token` on `serve`, or `SLACKX_RPC_TOKEN`) is set, every JSON-RPC request must send it as `Authorization: Bearer <token>` or `X-Slackx-Token: <token>`.
A non-loopback bind without a token is refused.

The server has no TLS.
When exposing it beyond your machine, put a TLS-terminating proxy in front of it.

## Python client

```python
import asyncio

from slackx.rpc.client import RpcClient


async def main() -> None:
    async with RpcClient("http://127.0.0.1:8280/rpc", token=None) as client:
        status = await client.call("cache.status")
        users = await client.call("users.list", {"limit": 20})
        print(status["message_count"], users["user_count"])


asyncio.run(main())
```

The client raises `slackx.rpc.protocol.RpcError` for JSON-RPC errors and `slackx.rpc.client.RpcTransportError` when the server cannot be reached.
