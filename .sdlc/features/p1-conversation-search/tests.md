---
title: "Conversation Search"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Conversation Search

## Scope

This plan covers the search command, the `fetch_search` orchestration, and the `search.messages` pager that already exist in the codebase.
It covers match caching, channel normalization, reply thread-root resolution, paging and limiting, `--full-threads` expansion, output formats, and the local full-text search.
It does not cover the web UI search page beyond the specific server tests cited below, nor channel fetch, polling, or thread display, which have their own features.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Search caches matches across threads (`test_cache.py::test_fetch_search_caches_matches_across_threads`) | Two matches in channels C1 and C2 | Both cached under their threads; `threads_seen/new` 2, `messages_seen/new` 2 |
| TC-2 | Object channel is normalized (`test_cache.py::test_fetch_search_normalizes_object_channel`) | Match with channel `{"id": "C1", "name": "general"}` | `matches[0]["channel"]` is `C1`; message cached under `C1` |
| TC-3 | Reply match keyed by permalink root (`test_cache.py::test_fetch_search_reply_match_keys_thread_by_permalink_root`) | Reply with `thread_ts` null and permalink carrying `thread_ts=1700000000.000100` | Cached under `1700000000.000100`, not under the reply ts |
| TC-4 | No matches returns empty result (`test_cache.py::test_fetch_search_no_matches_still_returns_empty`) | Empty match list | All counts zero and `matches == []` |
| TC-5 | Unchanged rerun reports zero (`test_cache.py::test_fetch_search_second_run_with_no_changes_reports_zero`) | Same matches twice | Second run `threads_new` 0 and `messages_new` 0 |
| TC-6 | Edited message reports one change (`test_cache.py::test_fetch_search_second_run_with_edited_message_reports_change`) | Two matches, then one with edited text | Second run `threads_new` 1 and `messages_new` 1; edited text cached |
| TC-7 | Local FTS finds inserted and edited messages (`test_storage.py::test_search_finds_inserted_and_edited_messages`) | Messages inserted then edited | `search_messages` returns the matching ts and drops the stale term |
| TC-8 | Local FTS defuses hostile query (`test_storage.py::test_search_query_syntax_is_defused`) | Operator-only and whitespace queries | `search_messages` returns `[]` without raising |
| TC-9 | Local FTS backfills old rows (`test_storage.py::test_search_backfills_rows_written_before_triggers`) | Rows written before the index existed | `ensure_search_index` backfills and search finds them |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-10 | Pager walks pages (`test_slack_api.py::test_iter_search_messages_paginates_by_page`) | Fake transport serving two pages | Matches from both pages yielded; first call URL is `/api/search.messages` |
| TC-11 | Limit caps total (`test_slack_api.py::test_iter_search_messages_limit_caps_total_matches`) | Three matches, `limit=3` | Exactly three matches yielded |
| TC-12 | Limit stops within a page (`test_slack_api.py::test_iter_search_messages_limit_stops_within_page`) | Page of matches, `limit=1` | One match yielded, no full page consumed |
| TC-13 | Limit zero fetches all pages (`test_slack_api.py::test_iter_search_messages_limit_zero_fetches_all_pages`) | Multi-page matches, `limit=0` | Every page fetched |
| TC-14 | Stops on a single page (`test_slack_api.py::test_iter_search_messages_stops_on_single_page`) | Single page | Pager stops after the first page |
| TC-15 | No matches is empty (`test_slack_api.py::test_iter_search_messages_no_matches_returns_empty`) | Page with no matches | No matches yielded |
| TC-16 | Full threads expand replies (`test_cache.py::test_fetch_search_full_threads_expands_replies`) | One match with a parent and reply | Both messages cached via replies; one replies call for the root |
| TC-17 | Full-threads reply match fetches the root (`test_cache.py::test_fetch_search_full_threads_reply_match_fetches_permalink_root`) | Reply match with permalink root | `conversations.replies` called for the root; parent and reply cached |
| TC-18 | Full-threads rerun reports zero (`test_cache.py::test_fetch_search_full_threads_second_run_reports_zero`) | Full-threads run twice | Second run `threads_new` 0 and `messages_new` 0 |
| TC-19 | Full threads survive payload drift (`test_cache.py::test_fetch_search_full_threads_handles_endpoint_payload_drift`) | Same message decorated differently by the two endpoints | Second run reports cache hits for every reply |
| TC-20 | Server FTS search (`test_server.py::test_search_fts`) | Cached messages, GET `/api/search?q=deploys` | JSON body lists the matching message |
| TC-21 | Server direct-channel hit resolves peer (`test_server.py::test_search_direct_channel_hit_resolves_peer_name`) | Cached direct channel, GET `/api/search?q=ping` | Body labels the hit with the peer name |
| TC-22 | Server hostile query is safe (`test_server.py::test_search_hostile_query_is_safe`) | Operator-only query | Request returns safely with no matches |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-23 | Human output and stderr summary (`test_cli.py::test_search_human_output`) | Run `conversations search hello` | Exit 0; stdout has the match, permalink, `1 match(es)`, and stderr shows the thread/message breakdown |
| TC-24 | JSON output (`test_cli.py::test_search_json_output`) | Run with `--json` | Exit 0; JSON has `query`, `match_count` 1, and the match text and channel |
| TC-25 | JSONL output (`test_cli.py::test_search_jsonl_output`) | Run with `--jsonl` | Exit 0; output is a single JSON line for the result set |
| TC-26 | Fields in JSON (`test_cli.py::test_search_fields_json`) | Run with `--json --fields text,channel,payload` | Emitted keys are exactly those three in order |
| TC-27 | Fields in human output (`test_cli.py::test_search_fields_human`) | Run with `--fields text` | Text is printed; channel and permalink are not |
| TC-28 | Invalid field rejected (`test_cli.py::test_search_invalid_fields`) | Run with `--fields bogus` | Exit 2 and stderr says `unknown field(s): bogus` |
| TC-29 | Direct channel peer name (`test_cli.py::test_search_direct_channel_hit_shows_peer_name`) | Fetch channels and users, then search | Output shows `[Tom Rochette (tomzx)]` and not `[D1]` |
| TC-30 | Count and sort flags (`test_cli.py::test_search_passes_count_sort_flags`) | Run with `--count 5 --sort score --sort-dir asc` | Client receives `count=5`, `sort=score`, `sort_dir=asc` |
| TC-31 | Limit flag (`test_cli.py::test_search_passes_limit_flag`) | Run with `--limit 2` | Client receives `limit=2` |
| TC-32 | Default limit (`test_cli.py::test_search_defaults_limit_to_cap`) | Run without `--limit` | Client receives `DEFAULT_SEARCH_LIMIT` |
| TC-33 | Match cached for show (`test_cli.py::test_search_caches_matches_for_show`) | Search, then `conversations get --no-fetch` | Cached search text is shown |
| TC-34 | Cached names rendered (`test_cli.py::test_search_renders_cached_user_and_channel_names`) | Fetch users and channels, then search with `--json` | Output uses cached user and channel names |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-35 | Slack returns an empty page | Pager stops and yields nothing further |
| TC-36 | Slack repeats a page number | Pager stops instead of looping forever |
| TC-37 | Match has no channel or no ts | The match is skipped rather than cached |
| TC-38 | `conversations.replies` returns nothing for a matched thread | The search match is cached directly as a fallback |
| TC-39 | FTS5 is unavailable in the SQLite build | `search_messages` returns `[]` and logs a warning instead of raising |
| TC-40 | `--limit 0` | Every page is fetched with no cap |

## Test Infrastructure

- `tests/test_cache.py` uses `FakeSearchClient`, an in-memory stand-in for `iter_search_messages` and `iter_thread_replies`, with a temporary SQLite database via `connect(tmp_path / "cache.db")`.
- `tests/test_cli.py` uses `FakeSearchClient` and monkeypatches `cli._internal._client._build_client`, with `capsys` for stdout/stderr assertions and a temporary database.
- `tests/test_slack_api.py` drives the real `SlackClient` through a fake httpx transport and collects the async iterator.
- `tests/test_storage.py` uses a temporary SQLite database and the `ensure_search_index` and `search_messages` helpers.
- `tests/test_server.py` uses FastAPI `TestClient` against a seeded cache.
- `tests/` runs under pytest with `testpaths=tests`; no network access is needed.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1, TC-23, TC-24 |
| FR-2 | TC-1, TC-33 |
| FR-3 | TC-2 |
| FR-4 | TC-3, TC-17 |
| FR-5 | TC-10, TC-14, TC-15, TC-35, TC-36 |
| FR-6 | TC-23 |
| FR-7 | TC-30 (base URL is exercised through `_build_client` in every CLI test) |
| FR-8 | TC-16, TC-18, TC-19 |
| FR-9 | TC-11, TC-12, TC-13, TC-31, TC-32, TC-40 |
| FR-10 | TC-30 |
| FR-11 | TC-30 |
| FR-12 | TC-24, TC-25 |
| FR-13 | TC-26, TC-27, TC-28 |
| FR-14 | TC-29, TC-34, TC-21 |
| FR-15 | TC-18, TC-19 |
| NFR-1 | TC-14, TC-15, TC-36 |
| NFR-2 | TC-16, TC-17 |
| NFR-3 | TC-10 (pager uses the shared client; rate-limit backoff is covered by `test_slack_api.py`) |
| NFR-4 | TC-8, TC-9, TC-22 |
| NFR-5 | TC-5, TC-18, TC-19 |
