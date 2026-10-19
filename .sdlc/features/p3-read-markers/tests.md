---
title: "Read markers (last-read tracking)"
status: done
session_link: http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ
---

# Test Plan: Read markers (last-read tracking)

## Scope

This plan covers the storage functions for last-read pointers, the `slackx conversations read` command group (mark, show, clear), the `slackx cache clear read` path, and the `/api/read` HTTP surface.
It does not cover Slack API fetching, message rendering, or channel and user caching beyond the fixtures they provide.
Tests live in `tests/test_storage.py`, `tests/test_cli.py`, and `tests/test_server.py`.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Channel and thread pointers are distinct rows | `set_last_read` for channel and for a thread root ts | Two rows, channel pointer has null thread ts, thread pointer has the root ts (`test_storage.py::test_set_and_get_last_read_scopes`) |
| TC-2 | Re-marking a scope updates the row | `set_last_read` twice with different timestamps | Marker count stays 1 and stored ts is the newer value (`test_storage.py::test_set_last_read_replaces_existing`) |
| TC-3 | Readers are independent | `set_last_read` for web then poll on the same channel | Each reader reads back its own ts and count is 2 (`test_storage.py::test_read_markers_are_per_reader`) |
| TC-4 | Listing filters and orders | Markers across readers and channels | Rows filtered by reader and channel, ordered by reader, channel, then scope (`test_storage.py::test_load_read_markers_filters_and_orders`) |
| TC-5 | Deleting one and many markers | `delete_read_marker` then `delete_read_markers` | Thread delete returns 1, missing delete returns 0, channel and reader deletes return their counts (`test_storage.py::test_delete_read_marker_and_markers`) |
| TC-6 | Newest cached ts per scope | Messages across a channel and a thread | Channel scope returns the newest message anywhere, thread scope returns that thread's newest, unknown channel returns None (`test_storage.py::test_latest_message_ts_channel_and_thread`) |
| TC-7 | Read-marker clear path | `clear_cache` with messages then read_markers | Clearing messages keeps markers, clearing read_markers removes 1 (`test_storage.py::test_clear_cache_read_markers`) |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-8 | Mark a channel defaults to newest | Seeded cache, `conversations read mark C1 --reader web` | Exit 0, one channel marker with the newest ts (`test_cli.py::test_read_mark_channel_defaults_to_latest`) |
| TC-9 | Reader defaults to default | Seeded cache, `conversations read mark C1` | Exit 0, marker owned by reader default (`test_cli.py::test_read_mark_default_reader`) |
| TC-10 | Thread scope via --ts | Seeded cache, `conversations read mark C1 --ts 1700000000.000100 --reader web` | Exit 0, one marker with that thread ts (`test_cli.py::test_read_mark_thread_scope`) |
| TC-11 | Explicit --last-read wins | Seeded cache, `conversations read mark C1 --last-read 1700000000.000050 --reader poll` | Exit 0, stored ts is the explicit value (`test_cli.py::test_read_mark_explicit_last_read`) |
| TC-12 | Mark with no cached messages | Cache without messages, `conversations read mark CNOPE --reader web` | Exit 1 and an error mentioning no cached messages (`test_cli.py::test_read_mark_without_cached_messages_errors`) |
| TC-13 | Show as JSON and unfiltered | Markers for web and poll | JSON lists only web when filtered, lists both readers when unfiltered (`test_cli.py::test_read_show_json`) |
| TC-14 | Show human-readable | One stored marker | Output contains the marker count, the reader, and the channel marker label (`test_cli.py::test_read_show_human`) |
| TC-15 | Clear scopes | Channel and thread markers for web | `--channel --ts` drops the thread pointer, `--channel` alone drops the channel markers (`test_cli.py::test_read_clear_scopes`) |
| TC-16 | Clear everything for one reader | Markers for web and poll | web markers are gone and poll markers remain (`test_cli.py::test_read_clear_all_for_reader`) |
| TC-17 | Cache clear read target | One stored marker plus other data | Read marker count is 0 and message count is unchanged (`test_cli.py::test_clear_read_markers_target`) |
| TC-29 | Show advances the pointer | Seeded cache, `conversations get C1 --reader web` | Printed output is normal and the web channel pointer is advanced to the newest ts (`test_cli.py::test_show_advances_read_marker`) |
| TC-30 | Show uses the default reader | Seeded cache, `conversations get C1` | The `default` reader's pointer is advanced (`test_cli.py::test_show_uses_default_reader`) |
| TC-31 | Show with nothing cached writes no marker | `conversations get CNOPE` | No marker is written (`test_cli.py::test_show_without_cached_messages_leaves_no_marker`) |

## End-To-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-18 | PUT defaults to newest and lists | PUT /api/read for channel C1, then GET /api/read | 200 with a channel marker holding the newest ts, GET returns read_count 1 (`test_server.py::test_read_marker_put_defaults_to_latest_and_lists`) |
| TC-19 | PUT thread scope and explicit value | PUT /api/read with thread_ts and last_read_ts | 200 and GET filtered by channel returns that thread marker and ts (`test_server.py::test_read_marker_thread_and_explicit_value`) |
| TC-20 | PUT unknown channel | PUT /api/read for channel CNOPE | 404 (`test_server.py::test_read_marker_put_unknown_channel_is_404`) |
| TC-21 | PUT blank reader | PUT /api/read with reader of spaces | 422 (`test_server.py::test_read_marker_put_blank_reader_is_422`) |
| TC-22 | DELETE scopes | PUT markers for web and poll, then DELETE by thread, by channel, and by reader | Each response body has the deleted count and the remaining count drops as expected (`test_server.py::test_read_marker_delete_scopes`) |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-23 | Mark with no cached messages and no explicit ts | Exit 1 and an error on stderr (`test_cli.py::test_read_mark_without_cached_messages_errors`) |
| TC-24 | Empty reader on mark | Exit 2 and an error on stderr |
| TC-25 | --ts given without --channel on clear | Exit 2 and an error saying --ts requires --channel |
| TC-26 | Blank reader over HTTP | HTTP 422 with a detail message |
| TC-27 | Delete a marker that does not exist | Deleted count is 0 and the call still succeeds (`test_storage.py::test_delete_read_marker_and_markers`) |
| TC-28 | Channel pointer and thread pointer for the same channel | Both rows exist and a channel-only delete keeps the thread pointers (`test_storage.py::test_set_and_get_last_read_scopes`) |

## Test Infrastructure

- Storage tests use the `connect` helper and `tmp_path` to open a fresh SQLite database per test.
- CLI tests drive `cli.main` with explicit `--db` paths and read back markers with the `_read_markers` and `_status_counts` helpers, seeding fixtures with `_seed_all_entities`.
- CLI output tests capture stdout and stderr with the pytest `capsys` fixture.
- Server tests use the FastAPI `TestClient` fixture over an app backed by a seeded cache database.
- All tests run under pytest with `testpaths=tests` and no network access.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1, TC-3, TC-8 |
| FR-2 | TC-1, TC-10, TC-19 |
| FR-3 | TC-3, TC-9, TC-16 |
| FR-4 | TC-6, TC-8, TC-18 |
| FR-5 | TC-11, TC-19 |
| FR-6 | TC-12, TC-20 |
| FR-7 | TC-24 |
| FR-8 | TC-13, TC-14 |
| FR-9 | TC-15, TC-16, TC-22 |
| FR-10 | TC-25 |
| FR-11 | TC-18, TC-19, TC-22 |
| FR-12 | TC-20, TC-21, TC-26 |
| FR-13 | TC-7, TC-17 |
| FR-14 | TC-29, TC-30, TC-31 |
| NFR-1 | TC-2 |
| NFR-2 | TC-1, TC-18 |
| NFR-3 | TC-13, TC-14 |
| NFR-4 | TC-4, TC-6 |
