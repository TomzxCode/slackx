---
title: "Channel Caching and Display"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Channel Caching and Display

## Scope

This plan covers the Slack channel listing and lookup in `slack_api.py` (`iter_channels`, `iter_channel_pages`, `get_channel_info`), the storage functions for the channels table (`upsert_channels`, `get_channel`, `load_channels`, `load_channel_display_names`, `load_im_channel_ids`, `list_channel_summaries`), the cache orchestration in `cache.py` (`fetch_channels`, `fetch_channel`), and the `slackx channels` command group (fetch, list).
It does not cover channel message fetching, thread caching, user caching, read markers, or the web UI.
Tests live in `tests/test_slack_api.py`, `tests/test_storage.py`, `tests/test_cache.py`, and `tests/test_cli.py`.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Channel listing passes the requested types and stops after one page | `iter_channels(types="public_channel")` against one page with no cursor | One channel id, one call to `/api/conversations.list` carrying that types value (`test_slack_api.py::test_iter_channels_passes_types_and_stops_without_cursor`) |
| TC-2 | Pagination yields one list per page and follows the cursor | Two pages, the second with an empty next cursor | Page ids split per call and the second call carries the first cursor (`test_slack_api.py::test_iter_channel_pages_yields_one_list_per_page`) |
| TC-3 | Single channel lookup uses conversations.info | `get_channel_info("C1")` | Channel dict returned and the request hits `/api/conversations.info` with that channel (`test_slack_api.py::test_get_channel_info_returns_channel`) |
| TC-4 | Single channel lookup degrades when Slack omits the channel | `get_channel_info("C1")` on an ok response with no channel | Empty dict (`test_slack_api.py::test_get_channel_info_empty_when_no_channel`) |
| TC-5 | Upsert then load preserves fields and ordering | Three channels, one public, one private, one with no visibility flag | Three rows written, loaded by id order, missing flag stays None, payload decoded (`test_storage.py::test_upsert_and_load_channels`) |
| TC-6 | Loading applies a SQL limit and can skip the payload column | Two seeded channels, then `load_channels(limit=1)` and `load_channels(include_payload=False)` | The limit returns one row, the no-payload load returns both with `payload == {}` and visibility intact (`test_storage.py::test_load_channels_limit_and_payload`) |
| TC-7 | Fetching an uncached channel returns None | `get_channel(conn, "C1")` on an empty table | None (`test_storage.py::test_get_channel_missing_returns_none`) |
| TC-8 | Upsert replaces an existing row | `upsert_channels` for C1 twice with different name, visibility, and time | Row count stays 1 and the newer name, visibility, and fetched_at win (`test_storage.py::test_upsert_channels_replaces_existing`) |
| TC-9 | Display names resolve direct message peers | Two direct channels with known peer users, one named channel, one direct channel with an unknown peer | Direct channels map to the peer's "Real name (handle)", the named channel maps to its name, and the unknown peer is omitted (`test_storage.py::test_load_channel_display_names_resolves_im_peer`) |
| TC-10 | Display names handle an empty request | `load_channel_display_names(conn, [])` | Empty dict (`test_storage.py::test_load_channel_display_names_empty_input`) |
| TC-11 | Direct message ids are detected from the payload | Mixed ids including a direct channel and a channel with `is_im` false | Only the direct channel id is returned (`test_storage.py::test_load_im_channel_ids`) |
| TC-12 | Direct message detection handles an empty request | `load_im_channel_ids(conn, [])` | Empty set (`test_storage.py::test_load_im_channel_ids_empty_input`) |
| TC-13 | Bulk channel fetch writes every channel and reports counts | Two channels through `fetch_channels` | processed 2, added 2, total 2, both cached, private flag stored (`test_cache.py::test_fetch_channels_caches_all`) |
| TC-14 | Single channel fetch caches one channel | `fetch_channel(conn, client, "C1")` | The returned channel has the id and name and is the only cached row (`test_cache.py::test_fetch_channel_caches_single`) |
| TC-15 | Single channel fetch returns None when Slack omits the channel | `fetch_channel` for a channel absent from the API | None returned and nothing cached (`test_cache.py::test_fetch_channel_returns_none_for_empty_payload`) |
| TC-16 | Bulk fetch persists each page before a later failure | A client that yields two pages then raises | The four channels from the completed pages stay cached and the failed page is absent (`test_cache.py::test_fetch_channels_persists_progress_before_failure`) |
| TC-17 | Channel summaries count messages and threads per channel | Two channels with messages across threads | Per-channel message and thread counts with the latest activity ts (`test_storage.py::test_list_channel_summaries_counts`) |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-18 | Bulk fetch then list in human form | Stub client returning one channel | Exit 0 and output shows the count, id, name, and "public" (`test_cli.py::test_fetch_channels_then_show`) |
| TC-19 | JSON list output | Stub client with one channel, `channels list --json` | Exit 0 and JSON has `channel_count` 1 and the channel with `is_private` false (`test_cli.py::test_show_channels_json`) |
| TC-20 | JSONL list output | Stub client with one channel, `channels list --jsonl` | Exit 0 and exactly one compact JSON line with the same fields (`test_cli.py::test_show_channels_jsonl`) |
| TC-21 | Listing a cached channel by id | Bulk fetch already run, `channels list C1 --no-fetch` | Exit 0 and output shows only the one channel (`test_cli.py::test_show_channels_single_cached`) |
| TC-22 | Limit caps the listing | Three seeded channels, `channels list --limit 2 --no-fetch` | Exit 0 and only the first two ids appear (`test_cli.py::test_show_channels_limit`) |
| TC-23 | Field selection in human form | Three seeded channels, `--fields id,is_private` | Exit 0 and output shows id plus "(private)" without the name (`test_cli.py::test_show_channels_fields_human`) |
| TC-24 | Field selection in JSON form | Seeded channels, `--json --fields id,display_name` | Exit 0 and the channel object holds only id and display_name (`test_cli.py::test_show_channels_fields_json`) |
| TC-25 | Direct channels render with the peer name | Cached users and a direct channel, `channels list --no-fetch` | Exit 0 and the direct channel renders as its peer name with "(direct)" (`test_cli.py::test_show_channels_labels_direct_channels`) |

## End-To-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-26 | Single channel fetch then list | Run `channels fetch C1`, then `channels list C1 --no-fetch` | First command exits 0 with "fetched channel C1 (general)" on stderr, second exits 0 and prints the channel (`test_cli.py::test_fetch_channels_single`) |
| TC-27 | Listing an uncached channel fetches it | Run `channels list C1 --json` with an empty cache | Exit 0 and JSON contains the fetched channel with its name (`test_cli.py::test_show_channels_single_fetches_when_missing`) |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-28 | Single channel fetch for an unknown id | Exit 1 and "error: channel C9 not found" on stderr (`test_cli.py::test_fetch_channels_single_unknown`) |
| TC-29 | Listing an uncached channel with --no-fetch | Exit 1 and "error: channel C9 is not cached" on stderr (`test_cli.py::test_show_channels_single_unknown_no_fetch`) |
| TC-30 | Slack omits the channel in a single lookup | `fetch_channel` returns None and leaves the cache unchanged (`test_cache.py::test_fetch_channel_returns_none_for_empty_payload`) |
| TC-31 | Bulk fetch interrupted mid pagination | Pages already received stay cached (`test_cache.py::test_fetch_channels_persists_progress_before_failure`) |
| TC-32 | Visibility flag missing from the payload | `is_private` stored and loaded as None, not coerced to False (`test_storage.py::test_upsert_and_load_channels`) |
| TC-33 | Direct channel whose peer is not cached | Display name lookup omits the channel and the caller falls back to the raw id (`test_storage.py::test_load_channel_display_names_resolves_im_peer`) |
| TC-34 | Unknown field name passed to --fields | Exit 2 and an "unknown field(s)" error on stderr |

## Test Infrastructure

- Storage tests open a fresh SQLite database per test with the `connect` helper and `tmp_path`.
- Cache tests use async stub clients (`FakeListClient`, `FailingChannelClient`) driven with `asyncio.run`, plus `tmp_path` databases.
- Slack API tests use `FakeTransport` to return canned JSON and record calls, then collect async generators with the `_collect` helper.
- CLI tests call `cli.main` with an explicit `--db` path, stub the client by monkeypatching `cli._internal._client._build_client`, and capture output with the pytest `capsys` fixture.
- All tests run under pytest with `testpaths=tests` and no network access.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-01 | TC-1, TC-2, TC-13 |
| FR-02 | TC-3, TC-5, TC-13 |
| FR-03 | TC-8, TC-13 |
| FR-04 | TC-18, TC-21, TC-23, TC-25 |
| FR-05 | TC-19, TC-20, TC-24 |
| FR-06 | TC-27 |
| FR-07 | TC-1, TC-2, TC-13 |
| NFR-01 | TC-13, TC-26 |
