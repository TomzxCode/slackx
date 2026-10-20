---
title: "JSON-RPC API"
status: done
---

# Specification: JSON-RPC API

## Overview

The JSON-RPC API is a transport layer over the CLI's operations.
`slackx.rpc.server.add_rpc_routes` mounts `POST /rpc` on the FastAPI app built by `create_app`, so `slackx serve` and `slackx rpc serve` expose the API next to the web UI.
`slackx.rpc.methods` holds the method registry, parameter validation, and handlers.
Handlers reuse the CLI helpers (`_client`, `_resolve_target`, `storage`, `cache`) and the shared payload builders in `cli/_internal/_render.py`, so the JSON shapes match `--json`.

## Architecture

```mermaid
flowchart LR
    Client["Client program"]
    CLI["slackx rpc call"]
    SPA["Web UI"]
    App["FastAPI app (server/app.py)"]
    RPC["rpc/server.py POST /rpc"]
    Methods["rpc/methods.py registry"]
    Helpers["CLI helpers: _client, _refs, _fields"]
    Store["storage.py (SQLite)"]
    Slack["cache.py + SlackClient"]

    Client -->|"JSON-RPC over HTTP"| RPC
    CLI -->|"RpcClient (httpx)"| RPC
    SPA -->|"/api/*"| App
    App --> RPC
    RPC --> Methods
    Methods --> Helpers
    Methods --> Store
    Methods -->|"fetch methods only"| Slack
```

The server binds one database path and one Slack API base URL when it starts.
Every handler receives an `RpcContext` with those values and builds a `CommonArgs` with `db` set, so the CLI's workspace resolution returns the bound database without another `auth.test`.

## Transport

`POST /rpc` accepts `application/json`.

| Body | Behavior |
|---|---|
| Single request object | One response object |
| Array of requests | Array of responses, in request order, with notifications omitted |
| Empty array | One `-32600` error object |
| Request object without `id` | Handler runs, HTTP 204, no body |
| Invalid JSON | HTTP 200 with `-32700` |
| Invalid request object | HTTP 200 with `-32600` |

Request-level failures always use HTTP 200, as JSON-RPC 2.0 requires for application and request errors.
HTTP 204 is used only when a batch yields no responses.

When the server is configured with a token, every request must send it as `Authorization: Bearer <token>` or `X-Slackx-Token: <token>`, compared in constant time.
A missing or wrong token gets HTTP 401 with a `WWW-Authenticate` header.
The token comes from `--token` or `SLACKX_RPC_TOKEN`.
`rpc serve` and `serve` refuse a non-loopback `--host` without a token, and both take an execution toggle (`--allow-exec` on `rpc serve`, `--rpc-allow-exec` on `serve`, default true) to control `cli.run`.

## Request validation

`rpc/protocol.py::parse_request` enforces:

| Field | Rule |
|---|---|
| `jsonrpc` | Exactly `"2.0"` |
| `method` | Non-empty string |
| `params` | JSON object or absent; absent becomes `{}`; arrays are rejected |
| `id` | String, number, or null when present; a boolean is rejected |
| `id` presence | Absence marks the request as a notification |

Each handler calls `_check_params(params, allowed)` first, so unknown parameters are `-32602`.
Typed helpers validate strings, booleans, integers, choices, and field lists.

## Errors

| Code | Meaning | Source |
|---|---|---|
| `-32700` | Parse error | Body is not JSON |
| `-32600` | Invalid request | `parse_request` validation, empty batch |
| `-32601` | Method not found | Registry lookup |
| `-32602` | Invalid params | Unknown parameter, wrong type, missing required parameter |
| `-32603` | Internal error | Reserved; not currently emitted |
| `-32000` | Server error | Application failure: missing cache row, no credentials, Slack error, unexpected exception |

`dispatch` converts `SystemExit` from CLI helpers into `-32000` with its message, and any other exception into `-32000` named by exception type.
It logs the failure with structlog and never returns a traceback.

## Method registry

`rpc/methods.py` defines a `Method` dataclass and a `@method(name, description, params)` decorator.
`_METHODS` maps names to handlers, and `list_methods(allow_exec)` returns the catalog sorted by name, omitting `cli.run` when execution is disabled.
`rpc.discover` returns the server name, version, and that catalog.
`system.methods` is kept as an alias for clients written against the first revision.
`server.info` reports the workspace, database path, API base URL, execution setting, method count, and start time.
`cli.run` runs `python -m slackx` with the forwarded args plus the server's `--db`, `--api-base-url`, and `--log-level` flags, and returns stdout, stderr, and the exit code.
`dispatch` rejects `cli.run` with `-32601` when execution is disabled, so hiding it from the catalog and refusing it agree.

Handlers are `async def handler(ctx: RpcContext, params: dict) -> Any`.
Network-touching imports (`cache`, `slack_api`, `workspace`) stay inside handlers or helpers, consistent with the CLI's lazy-import rule.

## Methods

| Method | Parameters (all optional unless noted) | Result |
|---|---|---|
| `rpc.discover` | none | `{name, version, methods: [{name, description, params}]}` |
| `system.methods` | none | Alias of `rpc.discover`, returning `{"methods": [...]}` |
| `server.info` | none | `{name, version, workspace, dbPath, apiBaseUrl, execEnabled, methods, startedAt}` |
| `cli.run` | `args` (required array), `stdin` | `{stdout, stderr, exitCode}` |
| `cache.status` | none | `{workspace, db_path, ...DbStatus}` |
| `cache.clear` | `target`: `all` (default), `messages`, `channels`, `users`, `read` | `{messages, threads, channels, users, read_markers}` |
| `users.list` | `limit` (0), `fields`, `fetch` (true) | `{user_count, users}` |
| `users.get` | `user` (required), `fields`, `fetch` (true) | `{user_count, users}` with one user |
| `channels.list` | `limit` (0), `fields`, `fetch` (true) | `{channel_count, channels}` |
| `channels.get` | `channel` (required), `fields`, `fetch` (true) | `{channel_count, channels}` with one channel |
| `conversations.fetch` | `target` (required), `ts`, `full_threads` (false), `last` (`1d`) | `{kind, ...fetch counts}` |
| `conversations.get` | `target` (required), `ts`, `fetch` (null), `with_thread_message` (false), `last` (`1d`), `reader` (`default`) | Thread or channel payload |
| `conversations.search` | `query` (required), `count` (20), `limit` (200), `sort` (`timestamp`), `sort_dir` (`desc`), `full_threads` (false), `fields` | `{query, match_count, matches, stats}` |
| `read.mark` | `target` (required), `ts`, `reader` (`default`), `last_read` | `{marker}` |
| `read.show` | `reader`, `channel` | `{read_count, markers}` |
| `read.clear` | `reader` (required), `channel`, `ts` | `{deleted}` |

`target` accepts a permalink, a channel id, a channel name (`general` or `#general`), or a user id or `@handle` for that direct message.

### Result payloads

| Payload | Builder | Keys |
|---|---|---|
| Thread | `_thread_payload` | `channel`, `channel_name`, `thread_ts`, `message_count`, `messages` |
| Channel | `_channel_payload` | `channel`, `channel_name`, `message_count`, `messages` |
| Search | `_search_payload` | `query`, `match_count`, `matches`; the RPC adds `stats` |
| Users | `_users_payload` | `user_count`, `users` |
| Channels | `_channels_payload` | `channel_count`, `channels` |

The CLI JSON renderers call the same builders, so the two surfaces cannot drift.

## Fetch policy

`conversations.get` mirrors the CLI:

| `fetch` | Behavior |
|---|---|
| absent / null | Fetch only when the target is not cached |
| `true` | Always refresh |
| `false` | Never fetch |

`users.list`, `channels.list`, `users.get`, and `channels.get` use `fetch: true` by default and fetch only when the cache has no rows (list) or the entity is missing (get).

`cache.clear` never prompts.
The RPC call is the explicit action; there is no interactive terminal to confirm on.

## CLI

| Command | Behavior |
|---|---|
| `slackx rpc serve` | Starts the same uvicorn app as `slackx serve`; `--host`, `--port`, `--token`, `--allow-exec` |
| `slackx rpc methods` | Calls `rpc.discover` and prints a method table, or JSON with `--json` |
| `slackx rpc call METHOD [PARAMS]` | Calls a method and prints pretty JSON; `--compact` prints one line |
| `slackx rpc exec -- ARGS...` | Runs a command through `cli.run`, forwards output and exit code |
| `slackx --remote [URL] COMMAND` | Runs any command through `cli.run`; `--rpc-token` sets the token |

`rpc call` takes the parameters as JSON in the second argument, or from `-` (stdin) or `@path`.
The older `--params` and `--params-file` flags remain.
The endpoint is `--url`/`--server`, then `SLACKX_RPC_URL`, then `http://127.0.0.1:8280/rpc`.
A bare host or host:port normalizes to `/rpc`.
JSON-RPC errors go to stderr and exit 1; malformed local parameters exit 2.
Remote execution mirrors the child's stdout, stderr, and exit code, and forwards piped stdin.

## Python client

`slackx.rpc.client.RpcClient` wraps an `httpx.AsyncClient`.
`call(method, params)` assigns an incrementing id, posts the request with the bearer token when set, raises `RpcError` for an error object, and raises `RpcTransportError` for connection, HTTP, or invalid-JSON failures.
`methods()` is a convenience over `rpc.discover`, and `exec(args, stdin)` is a convenience over `cli.run`.
`endpoint_url` normalizes a bare host, a host:port, or a URL without a path to `/rpc`.
The client owns its transport unless one is injected, and supports `async with`.

## Security

- No authentication is added; the server binds to loopback by default, matching the existing web UI.
- The client cannot choose the database, workspace, or Slack base URL.
- Credentials stay in the server process's environment or config file.
- `SLACK_TOKEN` and cookies are never included in a response.

## Decisions

- JSON-RPC over HTTP on the existing FastAPI app, rather than a separate server, so the web UI and API share one process and one database connection policy.
- Typed methods per CLI operation, rather than one `cli.run(argv)` passthrough, so clients get structured results and stable error codes instead of rendered text.
- Results reuse the CLI's JSON payload builders, so `--json` and RPC stay aligned.
- Parameter objects only, so validation is uniform and unknown options are caught.
- Long-running commands (`poll`, `serve`) stay out of the request/response surface.
- No new dependency: the transport is FastAPI, and the client uses httpx, both already required.
