---
title: "Fake Slack Server"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Fake Slack Server

## Scope

The fake Slack server is covered by `tests/test_fake_slack.py`, a single test module that exercises the package through its public API and over HTTP.
In scope: deterministic workspace generation, cursor pagination, every served endpoint, rate-limit simulation, epoch-base parsing, and the end-to-end slackx caching pipeline against the running server.
Out of scope: the CLI argument surface of `slack-fake-server` (not exercised), terminal rendering, and the web UI.

The test names below cite the real tests in `tests/test_fake_slack.py`.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `test_default_workspace_dimensions` | `Workspace(seed=42)` | 20 users, 17 channels (13 channels plus 4 direct messages), 4 direct messages, 30 threads |
| TC-2 | `test_custom_dimensions` | `WorkspaceParams(num_users=5, num_channels=3, num_ims=2, num_threads=10, min=2, max=4)` | 5 users, 5 channels, 2 direct messages, 10 threads |
| TC-3 | `test_ims_reference_existing_users` | `Workspace(seed=42)` | Direct message channels carry no `name` and their `user` is a generated user id |
| TC-4 | `test_ims_have_threads` | `Workspace(seed=42)` | Direct message channel ids intersect the thread channel ids |
| TC-5 | `test_same_seed_produces_same_data` | `Workspace(seed=42)` twice | Identical first user id, first channel id, and thread keys |
| TC-6 | `test_different_seed_produces_different_data` | `Workspace(seed=42)` and `Workspace(seed=99)` | User lists differ |
| TC-7 | `test_zero_activity_ratio_minimal_participants` | `activity_ratio=0.1, num_threads=5` | 5 threads are still generated |
| TC-8 | `test_high_num_users` | `num_users=100, num_threads=5` | 100 users |
| TC-9 | `test_large_workspace` | 100 users, 25 channels, 6 direct messages, 50 threads | 100 users, 31 channels, 50 threads |
| TC-10 | `test_small_workspace` | 3 users, 2 channels, 0 direct messages, 5 threads, 2 to 3 messages each | Requested counts, every thread has 2 to 3 messages |
| TC-11 | `test_single_channel` | `num_channels=1, num_threads=5` | All threads belong to the single channel |
| TC-12 | `test_messages_per_thread_ratio` | 20 threads with `min_messages_per_thread=4` and `max_messages_per_thread=4` | Every thread has at least 4 messages |
| TC-13 | `test_post_message_directly_on_workspace` | `Workspace.post_message` for a new thread | Key `(channel, ts)` exists and its first message text matches |
| TC-14 | `test_post_reply_directly_on_workspace` | `Workspace.post_message` with a `thread_ts` | The thread grows by one message |
| TC-15 | `test_default_disabled` | `RateLimiter(limits={"/api/test": 2})`, first check | Allowed |
| TC-16 | `test_returns_false_when_exceeded` | Limit 2 with a fixed clock, third check | Not allowed and `retry_after >= 1` |
| TC-17 | `test_unknown_path_always_allowed` | Limit on `/api/test`, repeated checks on `/api/other` | Always allowed |
| TC-18 | `test_per_endpoint_independent` | Limits `{"/api/a": 1, "/api/b": 1}` | `/api/a` blocked while `/api/b` is allowed |
| TC-19 | `test_succeeds_after_window_expires` | Clock advanced by `retry_after` | Request allowed again |
| TC-20 | `test_real_slack_tiers` | `ENDPOINT_RATE_LIMITS` | `conversations.replies` 50, `users.list` 20, `conversations.list` 20 |
| TC-21 | `test_default_epoch_base_is_jan_2024` | `DEFAULT_EPOCH_BASE` | 1704067200.0, which is 2024-01-01 |
| TC-22 | `test_custom_epoch_base_shifts_thread_timestamps` | `epoch_base=1750000000.0` | Same thread keys with timestamps shifted by the same delta |
| TC-23 | `test_recent_epoch_base_produces_recent_messages` | `epoch_base` one hour before now | Every root timestamp is within the last 7 days |
| TC-24 | `test_parse_epoch_base_now` | `"now"` | Within 2 seconds of the current time |
| TC-25 | `test_parse_epoch_base_iso_date` | `"2025-06-01"` | 1748736000.0 |
| TC-26 | `test_parse_epoch_base_numeric` | `"1750000000"` | 1750000000.0 |
| TC-27 | `test_parse_epoch_base_none_returns_default` | `None` | `DEFAULT_EPOCH_BASE` |
| TC-28 | `test_parse_epoch_base_invalid_raises` | `"not-a-date"` | `ValueError` matching `cannot parse` |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-29 | `test_returns_workspace_identity` | Module-scoped server fixture | `GET /api/auth.test` returns `ok`, `team_id == "T01FAKEWK"`, `url == "https://fake.slack.com/"`, user id starts with `U` |
| TC-30 | `test_user_matches_generated_workspace` | Module-scoped server fixture | The `auth.test` user equals the first member from `users.list` |
| TC-31 | `test_returns_all_users` | Module-scoped server fixture | `GET /api/users.list` returns `ok` and 20 members |
| TC-32 | `test_users_have_required_fields` | Module-scoped server fixture | Every member has `id`, `name`, `real_name`, and `profile.real_name` |
| TC-33 | `test_pagination` | Module-scoped server fixture | `limit=8` yields pages of 8, 8, 4, and the last `next_cursor` is empty |
| TC-34 | `test_all_pages_cover_every_user` | Module-scoped server fixture | Walking pages of 5 returns all 20 distinct user ids |
| TC-35 | `test_returns_user_by_id` | Module-scoped server fixture | `GET /api/users.info` returns the matching user id and name |
| TC-36 | `test_unknown_user_returns_error` | Module-scoped server fixture | `GET /api/users.info` with `U9999` returns 404 and `user_not_found` |
| TC-37 | `test_returns_all_channels` | Module-scoped server fixture | `GET /api/conversations.list` returns `ok` and 17 channels |
| TC-38 | `test_channels_have_required_fields` | Module-scoped server fixture | Every channel has `id` and `is_im`, and non-direct channels also have `name` and `is_private` |
| TC-39 | `test_filter_public_channels` | Module-scoped server fixture | `types=public_channel` returns only non-private channels |
| TC-40 | `test_filter_private_channels` | Module-scoped server fixture | `types=private_channel` returns only private channels |
| TC-41 | `test_pagination` | Module-scoped server fixture | `limit=5` returns 5 channels with a cursor, then 5 more |
| TC-42 | `test_filter_with_type_exclusion` | Module-scoped server fixture | `types=private_channel,im` returns only private or direct channels |
| TC-43 | `test_returns_channel_by_id` | Module-scoped server fixture | `GET /api/conversations.info` returns the matching channel id |
| TC-44 | `test_unknown_channel_returns_error` | Module-scoped server fixture | `GET /api/conversations.info` with `C9999` returns 404 and `channel_not_found` |
| TC-45 | `test_returns_thread_messages` | Module-scoped server fixture | `conversations.replies` for the first thread returns `ok` and at least one message |
| TC-46 | `test_messages_have_required_fields` | Module-scoped server fixture | Every reply has `ts`, `user`, `text`, and `thread_ts` |
| TC-47 | `test_oldest_filters_messages` | Thread with at least 3 messages | Every returned `ts` is greater than or equal to the `oldest` value |
| TC-48 | `test_nonexistent_thread_returns_error` | Module-scoped server fixture | Unknown channel and `ts` returns `ok: false` with an error |
| TC-49 | `test_pagination` | Thread with more than 4 messages | `limit=2` returns 2 messages, `has_more` is true, and page 2 starts at a different `ts` |
| TC-50 | `test_returns_404` | Module-scoped server fixture | `GET /api/unknown.method` returns 404 and `ok: false` |
| TC-51 | `test_users_stable_across_requests` | Module-scoped server fixture | Two `users.list` calls return the same ordered ids |
| TC-52 | `test_channels_stable_across_requests` | Module-scoped server fixture | Two `conversations.list` calls return the same ordered ids |
| TC-53 | `test_thread_stable_across_requests` | Module-scoped server fixture | Two `conversations.replies` calls return the same ordered timestamps |
| TC-54 | `test_returns_top_level_messages` | Channel that has threads | `conversations.history` returns `ok` and at least one message |
| TC-55 | `test_each_message_is_thread_root` | Channel that has threads | Every history message has `ts == thread_ts` |
| TC-56 | `test_reply_count_matches_thread` | Channel that has threads | `reply_count` equals the thread length minus one |
| TC-57 | `test_message_count_matches_thread_count` | Channel that has threads | The union of paginated history messages equals the number of threads in the channel |
| TC-58 | `test_pagination` | Channel with at least 3 threads | `limit=2` returns 2 messages with `has_more`, and page 2 starts at a different `ts` |
| TC-59 | `test_empty_channel_returns_empty` | Module-scoped server fixture | `conversations.history` for `C9999` returns `ok` and an empty message list |
| TC-60 | `test_messages_sorted_chronologically` | Channel that has threads | History timestamps are in ascending order |
| TC-61 | `test_returns_matches_with_required_fields` | A real workspace token is used as the query | `search.messages` returns `ok`, echoes the query, reports total and page counts, and every match has `ts`, `channel`, and `permalink` |
| TC-62 | `test_match_channel_is_real_channel` | A real workspace token is used as the query | Every match `channel.id` is a real generated channel id |
| TC-63 | `test_total_count_matches_workspace` | A real workspace token is used as the query | Reported total equals the number of workspace messages containing the term |
| TC-64 | `test_unknown_term_returns_zero_matches` | Query `zzznotaword12345` | `ok`, total 0, no matches, `page_count` 1 |
| TC-65 | `test_pagination_splits_matches` | A term with at least 3 matches | `count=2` returns 2 matches with `page_count >= 2` and non-overlapping timestamps across pages |
| TC-66 | `test_and_semantics_for_multiple_terms` | Two terms that co-occur | Every match text contains all query terms |
| TC-67 | `test_search_highlights_query_terms_with_backticks` | A real term | Match text contains the term in backticks, while the same message from `conversations.replies` is plain |
| TC-68 | `test_search_omits_thread_ts_for_thread_parents` | A real term | Any `thread_ts` on a match differs from its `ts` |
| TC-69 | `test_search_omits_parent_user_id` | A real term | No match has `parent_user_id` |
| TC-70 | `test_search_omits_edited_field` | A term matching an edited message | Search omits `edited` while `conversations.replies` includes it |
| TC-71 | `test_search_response_includes_permalink_and_channel_object` | A real term | Each match has a `channel` object with `id` and `name`, and a permalink starting with `https://acme.slack.com/archives/` |
| TC-72 | `test_normal_requests_succeed` | Rate-limited server fixture | `users.list` returns 200 and `ok` |
| TC-73 | `test_returns_429_when_limit_exceeded` | Rate-limited server fixture, 20 prior requests | The next request returns 429 with `error: "ratelimited"` and `Retry-After >= 1` |
| TC-74 | `test_rate_limit_is_per_endpoint` | Rate-limited server fixture | After exhausting `users.list`, `conversations.list` still returns 200 |
| TC-75 | `test_post_new_thread_via_api` | Module-scoped server fixture | `POST /api/chat.postMessage` returns `ok`, echoes channel and text, and `message.thread_ts == ts` |
| TC-76 | `test_posted_thread_appears_in_history` | Module-scoped server fixture | The posted `ts` appears in `conversations.history` |
| TC-77 | `test_post_reply_via_api` | Module-scoped server fixture | A reply carries the given `thread_ts` and a non-null `parent_user_id` |
| TC-78 | `test_post_reply_to_nonexistent_thread` | Module-scoped server fixture | Returns 404 and `thread_not_found` |
| TC-79 | `test_post_without_channel_returns_error` | Module-scoped server fixture | Returns 400 |
| TC-80 | `test_post_without_text_returns_error` | Module-scoped server fixture | Returns 400 |
| TC-81 | `test_post_message_with_custom_user` | Module-scoped server fixture | The returned message `user` echoes the supplied id |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-82 | `test_fetch_top_level_only` | Run `fetch_channel_messages` against the fake server into a `tmp_path` database | `fetched_messages` and `total_messages` equal the channel thread count, and `threads_with_replies_fetched` is 0 |
| TC-83 | `test_fetch_full_threads` | Run `fetch_channel_messages(..., full_threads=True)` | Totals equal the sum of all message lengths in the channel and `threads_with_replies_fetched` equals the thread count |
| TC-84 | `test_fetch_then_show_thread` | Fetch a channel, then call `load_thread` for one thread | The cached thread has a single root message with the expected timestamp |
| TC-85 | `test_fetch_search_caches_matches` | Run `fetch_search` for a real term | At least one match and new thread, and every match carries `channel` and `permalink` |
| TC-86 | `test_fetch_search_full_threads_then_show` | Run `fetch_search(..., full_threads=True)`, then `load_thread_messages` | At least one matched thread has more than one cached message |
| TC-87 | `test_fetch_search_full_threads_second_run_reports_cache_hits` | Run `fetch_search(..., full_threads=True)` twice | The second run reports the same matches, zero new threads, and zero new messages |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-88 | Rate-limit window rolls over | After waiting `retry_after`, the request is allowed again (TC-19) and the live server returns 200 (TC-73) |
| TC-89 | Last page of a cursor walk | `next_cursor` is an empty string when there are no more pages (TC-33, TC-34) |
| TC-90 | Re-running with the same seed | Identical workspace data (TC-5) and stable ids across requests (TC-51, TC-52, TC-53) |
| TC-91 | Recent epoch base | All root timestamps fall within the last 7 days (TC-23) |
| TC-92 | Unparseable epoch base | Raises `ValueError` (TC-28) |
| TC-93 | Empty channel history | Returns an empty message list (TC-59) |
| TC-94 | Unknown user, channel, thread, or endpoint | Returns 404 with a specific error code (TC-36, TC-44, TC-48, TC-50) |
| TC-95 | Missing `channel` or `text` on `chat.postMessage` | Returns 400 (TC-79, TC-80) |
| TC-96 | Search with no matching term | Returns zero matches without an error (TC-64) |
| TC-97 | Search versus replies drift | Backtick highlighting, omitted `thread_ts`, `parent_user_id`, and `edited` in search are all handled by the cache (TC-67 to TC-71, TC-87) |

## Test Infrastructure

- `_silence_logging` autouse fixture reconfigures structlog to `CRITICAL` so server logs do not pollute test output.
- `fake_server` (module scope) starts an `HTTPServer` on `127.0.0.1:0` with a fresh `Workspace(seed=42)` assigned to `FakeSlackHandler.workspace`, and shuts the server down on teardown.
- `rate_limited_server` (module scope) assigns `RateLimiter()` to `FakeSlackHandler.rate_limiter` and resets it to `None` on teardown.
- `workspace` fixtures (function scope) return `Workspace(seed=42)` for the cache integration tests.
- `_get` is a small helper for JSON `GET` requests; `httpx.post` is used directly for POST and error-status assertions.
- Cache integration tests create a SQLite database under `tmp_path` with `connect` and point `SlackClient` at `f"{fake_server}/api"`.
- External dependencies are pytest and httpx only; no network access beyond the loopback fake server.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-01 | TC-31, TC-37, TC-45, TC-54, TC-75 |
| FR-02 | TC-5, TC-6 |
| FR-03 | TC-33, TC-34, TC-41, TC-49, TC-58, TC-65 |
| FR-04 | TC-30, TC-32 |
| FR-05 | TC-38, TC-39, TC-40, TC-42 |
| FR-06 | TC-45, TC-46, TC-60, TC-82 |
| FR-07 | TC-2, TC-9, TC-10, TC-11, TC-12 |
| FR-08 | TC-20, TC-72, TC-74 |
| FR-09 | TC-16, TC-73 |
| FR-10 | TC-54, TC-56, TC-57, TC-59 |
| FR-11 | TC-75, TC-76, TC-77, TC-78, TC-79, TC-80, TC-81 |
| NFR-01 | TC-5, TC-51, TC-52, TC-53 |
| NFR-02 | No direct test: no test asserts the generation time bound |
| NFR-03 | No direct test: fixtures bind `127.0.0.1`, but the `127.0.0.1` default of the `slack-fake-server` command is not asserted |
