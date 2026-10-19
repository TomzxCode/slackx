---
title: "Channel Message Fetching"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Channel Message Fetching

## Scope

Covers `cache.fetch_channel_messages` and its `ChannelFetchResult`, the
`slack_api.iter_channel_history` paginator, the `storage` reconciliation
helpers (`mark_channel_roots_deleted_not_in`, `mark_thread_messages_deleted_not_in`,
`count_channel_messages`), and the `conversations fetch <target> [--full-threads]`
CLI path including `--last`.
Out of scope: thread-only fetching (FEAT-0001), search expansion, user and
channel caching, the web UI, and rendering internals.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Channel history paginator follows the cursor across pages | Two stub pages, the first with `has_more` and a `next_cursor` | Messages `1.0, 2.0, 3.0`; first call hits `/api/conversations.history` with `channel=C1`, second call passes `cursor=page2` (test_iter_channel_history_follows_cursor) |
| TC-2 | Channel history paginator stops when `has_more` is absent | One stub page with a single message | One message returned and exactly one transport call (test_iter_channel_history_stops_without_has_more) |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-3 | Top-level fetch stores standalone messages and thread parents only | In-memory SQLite plus a fake channel client with three history messages, one a thread parent | `fetched_messages == 3`, `total_messages == 3`, `threads_with_replies_fetched == 0`, one history call and no replies call (test_fetch_channel_messages_stores_top_level_only) |
| TC-4 | `--full-threads` also fetches each thread's replies | Fake client with one threaded parent and one reply | `fetched_messages == 3`, `threads_with_replies_fetched == 1`, one history call and one replies call for the parent ts; parent deduplicated across endpoints (test_fetch_channel_messages_full_threads_fetches_replies) |
| TC-5 | A standalone message is stored as its own thread root | Fake client with one standalone history message | A thread state row exists for the message ts (test_fetch_channel_messages_standalone_messages_use_own_ts_as_thread_ts) |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-6 | Basic channel fetch through the CLI | `conversations fetch C1 --db ...` with a stubbed client | Exit code 0 (test_fetch_channel_messages_basic) |
| TC-7 | Channel fetch from a permalink URL | `conversations fetch --url https://.../archives/C1 --db ...` | Exit code 0 (test_fetch_channel_via_url) |
| TC-8 | `--full-threads` through the CLI | `conversations fetch C1 --full-threads --db ...` | Exit code 0 (test_fetch_channel_messages_full_threads) |
| TC-9 | Default lookback is one day | `conversations fetch C1 --db ...` with no `--last` | Exit code 0 and a non-null `oldest` passed to `iter_channel_history` (test_fetch_channel_default_last_is_one_day) |
| TC-10 | `--last all` fetches the full history | `conversations fetch C1 --last all --db ...` | Exit code 0 and `oldest` is `None` (test_fetch_channel_last_zero_fetches_all) |
| TC-11 | Showing a fetched channel can include replies | Fetch `C1 --full-threads`, then `conversations get C1 --with-thread-message --no-fetch --json` | Message texts are `parent, reply, standalone`; the parent is not flagged as a reply (test_show_channel_with_thread_message_json) |
| TC-12 | Channel name resolves to an id before fetching | Cache channels, then `conversations fetch general --db ...` | Exit code 0 and the summary reports the resolved id `C1` (test_fetch_channel_resolves_name) |
| TC-13 | Fetch requires a target | `conversations fetch --db ...` with no URL or target | The CLI exits via `SystemExit` (test_fetch_channel_requires_url_or_channel_ts) |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-14 | A message was edited and another was deleted on Slack between fetches | The edited row's text is overwritten; the deleted row's content is kept with `payload.deleted` true and `deleted_messages == 1`; `total_messages == 3` (test_fetch_channel_messages_marks_edits_and_deletions) |
| TC-15 | Windowed refetch with `oldest` where a recent message was deleted and an older one sits outside the window | The in-window deleted row is marked, the out-of-window row stays unmarked, both rows remain, and `deleted_messages == 1` (test_fetch_channel_messages_reconcile_respects_oldest_window) |
| TC-16 | A reply was deleted from a thread during a `--full-threads` refetch | The deleted reply row is kept and flagged, the surviving reply is not, and `deleted_messages == 1` (test_fetch_channel_messages_full_threads_marks_deleted_replies) |

## Test Infrastructure

- pytest with `testpaths=tests` and `addopts=-ra` (run via `uv run pytest`).
- SQLite databases created per test under `tmp_path` through `storage.connect`.
- Fake clients: `FakeChannelClient` and `FakeChannelClientWithHistory` in `tests/test_cli.py`, `FakeChannelClient` in `tests/test_cache.py`, each yielding fixed history or replies.
- `FakeTransport` in `tests/test_slack_api.py` returns canned JSON pages and records request URLs and params for the paginator tests.
- `monkeypatch` of `slackx.cli._internal._client._build_client` injects the fake client into CLI runs.
- No network access and no real Slack credentials are required.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-01 | TC-6, TC-7, TC-12, TC-13 |
| FR-02 | TC-3, TC-4, TC-5 |
| FR-03 | TC-1, TC-2 |
| FR-04 | TC-6, TC-12 |
| FR-05 | TC-4, TC-8, TC-11 |
| FR-06 | TC-4 |
| FR-07 | No dedicated test; exercised indirectly by the CLI end-to-end setup |
| FR-08 | TC-9, TC-10, TC-15 |
| NFR-01 | TC-1, TC-2 |
| NFR-02 | TC-4, TC-16 |
