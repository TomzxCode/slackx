---
title: "Thread Caching and Display"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Thread Caching and Display

## Scope

Covers fetching a Slack thread via `conversations fetch`, storing messages in SQLite, and displaying the thread via `conversations show` as human-readable text, JSON, or JSONL.
The cited tests come from tests/test_cache.py, tests/test_cli.py, tests/test_storage.py, and tests/test_slack_api.py.
Permalink parsing tests come from tests/test_urls.py.
Out of scope: channel message fetching, search, polling, read markers, the web API, and the fake Slack server.

## Unit Tests

| ID | Description | Input | Expected Output | Test |
|---|---|---|---|---|
| TC-1 | Thread state lookup returns None when absent | Unknown channel and thread_ts | None | tests/test_storage.py::test_thread_state_missing_returns_none |
| TC-2 | Thread refresh records last_fetched and latest_reply and updates on repeat | Two record_thread_refresh calls | Second call's latest_reply and last_fetched are stored | tests/test_storage.py::test_record_thread_refresh_updates_latest_reply |
| TC-3 | Upsert stores messages and loads them ordered by ts | Two messages | Two writes, loaded in ts order with extracted fields and payload | tests/test_storage.py::test_upsert_and_load_messages |
| TC-4 | Upsert replaces an existing row on edit | Same ts with changed text | One row holding the edited text | tests/test_storage.py::test_upsert_replaces_existing_message |
| TC-5 | Upsert reports zero writes for unchanged content | Identical message twice | One write, then zero writes | tests/test_storage.py::test_upsert_skips_unchanged_message |
| TC-6 | Upsert ignores blocks and attachment drift between endpoints | search.messages shape then conversations.replies shape | Second upsert writes zero and keeps the first blocks | tests/test_storage.py::test_upsert_ignores_blocks_drift_between_endpoints |
| TC-7 | Upsert keeps blocks and attachments in the payload | Message carrying blocks and attachments | Payload holds them and an identical refetch writes zero | tests/test_storage.py::test_upsert_stores_blocks_and_attachments |
| TC-8 | Upsert backfills blocks for legacy rows once | Legacy row then a blocks message | One backfill write, stable afterwards | tests/test_storage.py::test_upsert_backfills_blocks_for_legacy_rows |
| TC-9 | Upsert detects a text edit under stripped fields | Edited text plus volatile fields | One write | tests/test_storage.py::test_upsert_detects_text_edit_under_stripped_fields |
| TC-10 | FetchResult exposes channel, thread_ts, counts, and incremental | Constructed FetchResult | Fields match the inputs | tests/test_cli.py::test_fetch_result_dataclass_fields |
| TC-11 | Permalink parsing resolves channel and thread ts | Root and reply permalinks | ThreadRef with the correct channel and thread_ts | tests/test_urls.py::test_parse_thread_root_permalink, tests/test_urls.py::test_parse_reply_permalink_uses_thread_ts_query |
| TC-12 | Cursor pagination follows next_cursor | Two history pages with next_cursor | Items from both pages, second call carries the cursor | tests/test_slack_api.py::test_iter_channel_history_follows_cursor |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome | Test |
|---|---|---|---|---|
| TC-13 | Initial fetch stores the full thread | Empty cache | incremental False, two fetched, oldest None, latest_reply set | tests/test_cache.py::test_fetch_thread_initial_full_fetch |
| TC-14 | Second fetch is incremental with oldest=latest_reply | Thread already cached | incremental True, oldest is the prior latest_reply, three total | tests/test_cache.py::test_fetch_thread_incremental_uses_latest_reply |
| TC-15 | Incremental fetch with no new messages keeps state | Thread cached, second batch empty | Zero fetched, latest_reply unchanged | tests/test_cache.py::test_fetch_thread_incremental_with_no_new_messages_preserves_state |
| TC-16 | Incremental fetch overwrites an edited message | Thread cached, client returns edited text | Stored text is the edit | tests/test_cache.py::test_fetch_thread_updates_edited_message |
| TC-17 | Full fetch flags replies Slack no longer returns | force_full refetch, one reply missing | Missing reply kept and marked deleted, incremental False | tests/test_cache.py::test_fetch_thread_full_marks_deleted_replies |
| TC-18 | Incremental fetch does not mark deletions | Second incremental window omits the root | No message marked deleted | tests/test_cache.py::test_fetch_thread_incremental_does_not_reconcile |
| TC-19 | Edited metadata is stored in the payload | Message carrying edited data | Payload holds edited | tests/test_cache.py::test_fetch_thread_stores_edited_field |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome | Test |
|---|---|---|---|---|
| TC-20 | Show prints a human-readable thread | Fetch a single-message thread, run show with --no-fetch | Stdout has channel/ts, "1 message(s)", author, and text, not JSON | tests/test_cli.py::test_show_prints_human_readable_by_default |
| TC-21 | Show resolves the author to a cached display name | Fetch users, then show the thread | Author shown as "Alice Smith (alice)" | tests/test_cli.py::test_show_renders_user_name_when_cached |
| TC-22 | Show --json emits a structured thread | Show the cached thread with --json | JSON has channel, thread_ts, message_count, and message text | tests/test_cli.py::test_show_prints_json_with_flag |
| TC-23 | Show --jsonl emits a single JSON line | Show the cached thread with --jsonl | One line with channel, thread_ts, message_count, and text | tests/test_cli.py::test_show_prints_jsonl_with_flag |
| TC-24 | Fetch a thread from a permalink URL | Run fetch with a thread permalink | Exit 0, client receives oldest None | tests/test_cli.py::test_fetch_with_url |
| TC-25 | Fetch resolves a channel name before fetching the thread | Fetch channels, then fetch "#general" with --ts | Client receives channel id C1 | tests/test_cli.py::test_fetch_thread_resolves_channel_name |
| TC-26 | Fetch requires a target | Run fetch with no target | SystemExit | tests/test_cli.py::test_fetch_channel_requires_url_or_channel_ts |
| TC-27 | Show a channel without --ts prints human output | Cache channel messages, run show with --no-fetch | Exit 0, human output | tests/test_cli.py::test_show_channel_without_ts_human |
| TC-28 | Show a channel without --ts emits JSON | Cache channel messages, run show --json --no-fetch | JSON includes channel and resolved user names | tests/test_cli.py::test_show_channel_without_ts_json |
| TC-29 | Show a channel reads from the cache with --no-fetch | Cache channel messages, run show --no-fetch | Exit 0 rendering cached rows | tests/test_cli.py::test_show_channel_without_ts_uses_cached |
| TC-30 | Show a channel excludes thread replies by default | Fetch a channel with --full-threads, show --json | Only parent and standalone texts appear | tests/test_cli.py::test_show_channel_excludes_thread_replies |
| TC-31 | Show --with-thread-message includes replies | Fetch a channel with --full-threads, show with the flag | Replies appear in order, marked with their thread root | tests/test_cli.py::test_show_channel_with_thread_message_json, tests/test_cli.py::test_show_channel_with_thread_message_human |
| TC-32 | Show a channel by name | Cache channel names, show by name | Exit 0 | tests/test_cli.py::test_show_channel_with_name |
| TC-33 | A message cached by search is shown by show --no-fetch | Run search, then show the thread with --no-fetch | Cached text is printed | tests/test_cli.py::test_search_caches_matches_for_show |
| TC-34 | Show --json and --jsonl are mutually exclusive | Run show with both flags | SystemExit with "mutually exclusive" on stderr | tests/test_cli.py::test_show_json_and_jsonl_are_mutually_exclusive |
| TC-35 | Fetch prints a summary to stderr with the resolved channel | Fetch a channel by name | Stderr reports "for C1" | tests/test_cli.py::test_fetch_channel_resolves_name |
| TC-42 | Default show does not re-fetch a cached thread | Fetch a thread, then show it without flags using a client that would raise | Exit 0, cached text printed, no client call | tests/test_cli.py::test_show_default_does_not_refetch_cached_thread |
| TC-43 | show --fetch refreshes a cached thread | Fetch a thread, then show --fetch with a client returning a new reply | Exit 0, new reply printed, incremental fetch (oldest=latest reply) | tests/test_cli.py::test_show_fetch_refreshes_cached_thread |
| TC-44 | show --fetch refreshes a cached channel | Fetch a channel, then show --fetch with a client returning a new message | Exit 0, new message printed | tests/test_cli.py::test_show_channel_fetch_refreshes_cached |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior | Test |
|---|---|---|---|
| TC-36 | Unknown channel name on show | Exit 1, "could not resolve" on stderr | tests/test_cli.py::test_show_channel_unresolved_name_errors |
| TC-37 | Windowed refetch respects the lookback bound | Only in-window missing roots are marked deleted | tests/test_cache.py::test_fetch_channel_messages_reconcile_respects_oldest_window |
| TC-38 | Show an uncached scope with --no-fetch | Exit 0, nothing printed | tests/test_cli.py::test_show_without_cached_messages_leaves_no_marker |
| TC-39 | Lookback duration parsing | Duration strings parse to epoch timestamps | tests/test_cli.py::test_parse_duration |
| TC-40 | Channel fetch default and full lookback | Default is one day, "all" disables the bound | tests/test_cli.py::test_fetch_channel_default_last_is_one_day, tests/test_cli.py::test_fetch_channel_last_zero_fetches_all |
| TC-41 | Show a channel without --ts emits JSONL | One JSON line for the channel | tests/test_cli.py::test_show_channel_without_ts_jsonl |

## Test Infrastructure

- Tests use pytest with the `tmp_path` fixture for a fresh SQLite database per test.
- tests/test_cache.py defines FakeClient and FakeChannelClient doubles that record calls and replay fixed message batches, driving the async cache layer with `asyncio.run`.
- tests/test_cli.py drives the cyclopts app through `cli.main` and monkeypatches `cli._internal._client._build_client`, using `capsys` for stdout and stderr.
- tests/test_storage.py calls the storage functions directly against a temporary database.
- tests/test_slack_api.py wraps `httpx.AsyncClient` with `httpx.MockTransport` and a queued FakeTransport, with an autouse structlog fixture that silences per-page logs.
- No test opens a real Slack connection.
- `iter_thread_replies` has no direct httpx-level test; its cursor loop is covered indirectly by the FakeClient doubles in tests/test_cache.py and by the history-cursor unit test TC-12.
- Rate-limit retry (FR-12) has no dedicated test.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-01 | TC-11, TC-24 |
| FR-02 | TC-25, TC-26 (drift: the CLI takes a positional target plus --ts, not --channel) |
| FR-03 | TC-13, TC-24 (no httpx-level test of iter_thread_replies) |
| FR-04 | TC-3, TC-4, TC-5, TC-6, TC-16, TC-18 |
| FR-05 | TC-1, TC-2, TC-13 |
| FR-06 | TC-14, TC-15, TC-16 |
| FR-07 | TC-20 |
| FR-08 | TC-22, TC-23, TC-28, TC-41 |
| FR-09 | TC-29, TC-38, TC-42, TC-43, TC-44 |
| FR-10 | TC-21 |
| FR-11 | TC-12 (covers the shared cursor loop; iter_thread_replies has no direct test) |
| FR-12 | No dedicated test |
| FR-13 | TC-27, TC-28, TC-29, TC-30, TC-32, TC-41 |
| FR-14 | TC-21, TC-28 |
| FR-15 | TC-39, TC-40 (drift: the flag is --last, not --oldest) |
| NFR-01 | TC-5, TC-14, TC-15 |
| NFR-02 | TC-36 |
| NFR-03 | TC-35 |
