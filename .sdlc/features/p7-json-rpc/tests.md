---
title: "JSON-RPC API"
status: done
---

# Test Plan: JSON-RPC API

## Scope

This plan covers the JSON-RPC transport (`POST /rpc`), token authentication, request validation, the method registry and handlers, `cli.run`, the Python client, and the `rpc serve`, `rpc call`, `rpc methods`, `rpc exec`, and `--remote` CLI surfaces.
Endpoint cases drive the app through `fastapi.testclient.TestClient` against a seeded temporary database.
Fetch methods stub the Slack client and the cache fetch functions, so no network call is made.
The CLI cases replace `RpcClient` with an in-memory stand-in, except the parity case, which runs the real CLI against the same database.
Out of scope are a real uvicorn listener, real Slack traffic, the web UI routes that share the app, and long-running commands (`poll`, `serve`).

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Client returns a result | Mock transport answering a success object | The result value is returned (test_rpc.py, `test_client_call_and_error`) |
| TC-2 | Client raises on an error object | Mock transport answering `-32000` | `RpcError` with code `-32000` (test_rpc.py, `test_client_call_and_error`) |
| TC-3 | Client wraps a transport failure | Mock transport raising `ConnectError` | `RpcTransportError` (test_rpc.py, `test_client_transport_error`) |
| TC-4 | `rpc call` rejects non-object parameters | `--params '[1, 2]'` | Exit 2, stderr says the parameters must be a JSON object (test_rpc.py, `test_rpc_call_rejects_invalid_params_json`) |
| TC-5 | Unexpected handler failure hides the traceback | Handler raising `RuntimeError("kaboom")` | `-32000`, message `RuntimeError: kaboom`, no traceback text (test_rpc.py, `test_unexpected_exception_hides_traceback`) |

## Protocol and Transport Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-6 | Parse error | Body `{not json` | HTTP 200 and `-32700` (test_rpc.py, `test_parse_error`) |
| TC-7 | Invalid request object | Object without `jsonrpc` | `-32600` (test_rpc.py, `test_invalid_request_object`) |
| TC-8 | Unknown method | `does.not.exist` | `-32601` (test_rpc.py, `test_unknown_method`) |
| TC-9 | Unknown parameter | `users.list` with `nope` | `-32602` and the parameter name (test_rpc.py, `test_unknown_parameter_is_invalid_params`) |
| TC-10 | Wrong parameter type | `users.list` with `limit: "ten"` | `-32602` (test_rpc.py, `test_wrong_parameter_type_is_invalid_params`) |
| TC-11 | Missing required parameter | `users.get` with no `user` | `-32602` (test_rpc.py, `test_missing_required_parameter`) |
| TC-12 | Notification | Request without `id` | HTTP 204 and an empty body (test_rpc.py, `test_notification_returns_no_content`) |
| TC-13 | Batch with a result and an error | Two requests, one unknown method | Responses in request order, error on the second (test_rpc.py, `test_batch_mixes_results_and_errors`) |
| TC-14 | Empty batch | `[]` | One `-32600` error object (test_rpc.py, `test_empty_batch_is_invalid_request`) |
| TC-15 | Server-bound state | `db_path` or `api_base_url` in params | `-32602` (test_rpc.py, `test_database_and_api_base_are_not_client_settable`) |

## Method Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-16 | Method catalog | Seeded database | `rpc.discover` returns the server name, version, and every exposed method; `system.methods` remains an alias (test_rpc.py, `test_rpc_discover_lists_server_and_methods`, `test_system_methods_remains_an_alias`) |
| TC-16a | Server info | Seeded database | `server.info` reports the database path, execution setting, and start time (test_rpc.py, `test_server_info`) |
| TC-16b | Run a CLI command | Seeded database | `cli.run` exits 0 and prints the CLI's JSON status for the same database (test_rpc.py, `test_cli_run_executes_a_command`) |
| TC-16c | Execution disabled | `rpc_allow_exec=False` | `cli.run` is absent from the catalog and returns `-32601` (test_rpc.py, `test_cli_run_is_hidden_and_rejected_when_disabled`) |
| TC-16d | Token authentication | `rpc_token="secret"` | Requests without the token or with a wrong token get HTTP 401; both Bearer and `X-Slackx-Token` work (test_rpc.py, `test_rpc_requires_a_bearer_token`) |
| TC-17 | Users list from cache | Two cached users, `fetch: false` | `user_count` 2 and the first user's id, name, and real name (test_rpc.py, `test_users_list_uses_cache`) |
| TC-18 | User get with field selection | Cached user, `fields: ["id", "name"]` | One user with only those keys (test_rpc.py, `test_users_get_and_fields`) |
| TC-19 | User get on a cache miss | Missing user, `fetch: false` | `-32000` saying the user is not cached (test_rpc.py, `test_users_get_missing_is_server_error`) |
| TC-20 | Channels list from cache | One cached channel, `fetch: false` | `channel_count` 1 and the channel payload (test_rpc.py, `test_channels_list_uses_cache`) |
| TC-21 | Channel get by id | Cached `C1`, `fetch: false` | One channel payload (test_rpc.py, `test_channels_get_uses_cache`) |
| TC-22 | Channel get by cached name | Token `general`, `fetch: false` | Resolves to `C1` (test_rpc.py, `test_channels_get_resolves_cached_name`) |
| TC-23 | Channel get on a cache miss | Missing channel, `fetch: false` | `-32000` saying the channel is not cached (test_rpc.py, `test_channels_get_missing_is_server_error`) |
| TC-24 | Conversation channel view | Cached channel with one root message | Channel payload with resolved author name (test_rpc.py, `test_conversations_get_channel`) |
| TC-25 | Conversation thread view | Cached thread with a reply | Thread payload with both messages (test_rpc.py, `test_conversations_get_thread`) |
| TC-26 | Read pointer advances | `conversations.get` with `reader: "web"` | `read.show` reports the newest message ts (test_rpc.py, `test_conversations_get_advances_read_marker`) |
| TC-27 | Null reader writes nothing | `conversations.get` with `reader: null` | `read.show` reports no markers (test_rpc.py, `test_conversations_get_null_reader_does_not_mark`) |
| TC-28 | Unknown channel id returns empty | Target `C404`, `fetch: false` | Empty message list, no error (test_rpc.py, `test_conversations_get_unknown_id_returns_empty`) |
| TC-29 | Fetch a thread | Stubbed `fetch_thread`, `target` plus `ts` | `kind` is `thread` with the fetch counts (test_rpc.py, `test_conversations_fetch_thread`) |
| TC-30 | Fetch a channel | Stubbed `fetch_channel_messages`, `full_threads: true` | `kind` is `channel`, counts returned, `oldest` computed from `last` (test_rpc.py, `test_conversations_fetch_channel`) |
| TC-31 | Search | Stubbed `fetch_search` with one match | Match payload with user and channel names plus `stats` (test_rpc.py, `test_conversations_search`) |
| TC-32 | Read mark and clear | Mark for `web`, then clear with `channel` | Marker set to the newest ts, one marker deleted, `read.show` empty (test_rpc.py, `test_read_mark_and_clear`) |
| TC-33 | Read clear validates scope | `ts` without `channel` | `-32602` (test_rpc.py, `test_read_clear_requires_channel_for_ts`) |
| TC-34 | Cache status | Seeded database | Channel, user, and message counts plus a `db_path` (test_rpc.py, `test_cache_status`) |
| TC-35 | Cache clear by target | `target: "users"` | Two users removed, channels kept (test_rpc.py, `test_cache_clear_target`) |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-36 | Method list, human | `slackx rpc methods` with the stand-in client | Exit 0, a method table with name and description printed (test_rpc.py, `test_rpc_methods_lists_catalog`) |
| TC-37 | Method list, JSON | `slackx rpc methods --json` | Exit 0, the catalog printed as JSON (test_rpc.py, `test_rpc_methods_prints_json`) |
| TC-38 | Call prints JSON | `slackx rpc call users.list --params '{"fetch": false}'` | Exit 0, result printed as JSON, params forwarded (test_rpc.py, `test_rpc_call_prints_json`) |
| TC-39 | Call reports an RPC error | Stand-in client raising `RpcError` | Exit 1, error on stderr (test_rpc.py, `test_rpc_call_reports_rpc_error`) |
| TC-40 | RPC and CLI JSON parity | Same cached thread through `conversations.get` and `conversations get --json` | Both payloads are equal (test_rpc.py, `test_rpc_and_cli_json_payloads_match`) |
| TC-40a | Call with positional params | `slackx rpc call users.list '{"fetch": false}'` | Exit 0, params forwarded (test_rpc.py, `test_rpc_call_accepts_positional_params`) |
| TC-40b | Remote mode | `slackx --remote http://x conversations get C1` with a stand-in client | The command is forwarded to `cli.run`, output is mirrored, exit code is mirrored (test_rpc.py, `test_remote_forwards_to_cli_run`) |
| TC-40c | `rpc exec` | `slackx rpc exec --url http://x -- cache status --json` | Arguments are forwarded unchanged, output is mirrored (test_rpc.py, `test_rpc_exec_forwards_arguments`) |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-41 | Notification whose handler fails | No response body, HTTP 204 (server omits errored notifications) |
| TC-42 | Batch containing only notifications | HTTP 204 with no body |
| TC-43 | Missing Slack credentials on a fetch method | `SystemExit` from the CLI helper becomes `-32000` with its message |
| TC-44 | Unknown channel name in `channels.get` or `read.clear` | Resolution fails and the method returns `-32000` |
| TC-45 | `conversations.get` with `fetch: null` on an uncached target | Fetches once, matching the CLI's default fetch policy |
