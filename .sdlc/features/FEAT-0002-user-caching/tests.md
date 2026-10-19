---
title: "User Caching and Display"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: User Caching and Display

## Scope

This plan covers the user cache path that already exists in the codebase: the `users.list` and `users.info` pager methods, the `fetch_users` and `fetch_user` orchestration, the `users` storage table and its CRUD and display-name helpers, and the `users fetch`, `users list`, and `users get` commands.
It covers bulk and single-user fetching, upsert idempotency, the human, JSON, and JSONL output formats, field selection, limits, display-name resolution in thread and search rendering, and direct-message peer naming.
It does not cover channel caching, thread caching, search, polling, or the web UI except where a test exercises user names through those views.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Bulk fetch caches all users (`test_cache.py::test_fetch_users_caches_all`) | Users U1 and U2 | `processed` and `added` 2, `total` 2, both cached with names |
| TC-2 | Single fetch caches one user (`test_cache.py::test_fetch_user_caches_single`) | `fetch_user` for U1 via `users.info` | User returned with id U1 and name alice; U1 cached |
| TC-3 | Single fetch with empty payload (`test_cache.py::test_fetch_user_returns_none_for_empty_payload`) | `fetch_user` for an absent user | `None` returned and cache stays empty |
| TC-4 | Bulk fetch is idempotent (`test_cache.py::test_fetch_users_is_idempotent`) | `fetch_users` run twice | Second run `processed` 1, `added` 0, `total` 1 |
| TC-5 | Upsert and load users (`test_storage.py::test_upsert_and_load_users`) | Two users, one with only `profile.real_name` | Count 2, ordered by id, `real_name` falls back to the profile value |
| TC-6 | Load limit and payload flag (`test_storage.py::test_load_users_limit_and_payload`) | Three users, `limit=2` and `include_payload=False` | Limit caps rows to two; payload omitted when the flag is off |
| TC-7 | Missing user returns None (`test_storage.py::test_get_user_missing_returns_none`) | `get_user` for an uncached id | `None` |
| TC-8 | Display names resolve only requested (`test_storage.py::test_load_user_display_names_resolves_only_requested`) | `load_user_display_names` for U1 and U2 with U3 cached | Only U1 and U2 resolved, formatted `Real Name (handle)` |
| TC-9 | Display name formatting (`test_storage.py::test_load_user_display_names_formatting`) | Users with both names, handle only, and id only | `Real Name (handle)`, handle alone, and id alone |
| TC-10 | Display names with empty input (`test_storage.py::test_load_user_display_names_empty_input`) | Empty id list | Empty map |
| TC-11 | Display names dedupe ids (`test_storage.py::test_load_user_display_names_dedupes_ids`) | The same id three times | Single entry, no error |
| TC-12 | Upsert replaces existing (`test_storage.py::test_upsert_users_replaces_existing`) | Same id twice with new name and time | Name and `fetched_at` updated, count still 1 |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-13 | Pager follows the cursor (`test_slack_api.py::test_iter_users_follows_cursor`) | Fake transport serving two pages | Users from both pages yielded; first call URL is `/api/users.list`; cursor passed on the second call |
| TC-14 | Pager yields one list per page (`test_slack_api.py::test_iter_user_pages_yields_one_list_per_page`) | Fake transport serving two pages | One list per page, in page order, first call URL `/api/users.list` |
| TC-15 | `users.info` returns a user (`test_slack_api.py::test_get_user_info_returns_user`) | Fake transport serving a user | User returned with id and name; call URL `/api/users.info` with `user=U1` |
| TC-16 | `users.info` empty when absent (`test_slack_api.py::test_get_user_info_empty_when_no_user`) | Fake transport serving no user | Empty dict |
| TC-17 | Fetch then list (`test_cli.py::test_fetch_users_then_show`) | `users fetch` then `users list --no-fetch` | Exit 0; output has `1 user(s)`, id U1, name alice, and real name Alice Smith |
| TC-18 | Single fetch via `users.info` (`test_cli.py::test_fetch_users_single`) | `users fetch U1` | Exit 0; stderr has `fetched user U1 (Alice Smith)` |
| TC-19 | Single fetch of unknown id (`test_cli.py::test_fetch_users_single_unknown`) | `users fetch U9` | Non-zero exit with `error: user U9 not found` |
| TC-20 | Single cached user displayed (`test_cli.py::test_show_users_single_cached`) | `users fetch`, then `users get U1 --no-fetch` | Exit 0; output has `1 user(s)`, U1, and alice |
| TC-21 | Single uncached user fetched on get (`test_cli.py::test_show_users_single_fetches_when_missing`) | `users get U1 --json` with U1 uncached | Exit 0; JSON has `user_count` 1 and user U1 with name alice |
| TC-22 | Single uncached user with `--no-fetch` (`test_cli.py::test_show_users_single_unknown_no_fetch`) | `users get U9 --no-fetch` | Exit 1 with `error: user U9 is not cached` |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-23 | JSON output (`test_cli.py::test_show_users_json`) | Run `users list --json` | Exit 0; JSON has `user_count` 1 and user U1 with name alice |
| TC-24 | JSONL output (`test_cli.py::test_show_users_jsonl`) | Run `users list --jsonl` | Exit 0; output is a single compact JSON line with the user |
| TC-25 | Empty cache without fetch (`test_cli.py::test_show_users_no_fetch_empty`) | Run `users list --no-fetch` on an empty cache | Exit 0; output has `0 user(s)` |
| TC-26 | Limit flag (`test_cli.py::test_show_users_limit`) | Run `users list --no-fetch --limit 2` | Exit 0; output has `2 user(s)`, U1 and U2, and not U3 |
| TC-27 | Limit flag in JSON (`test_cli.py::test_show_users_limit_json`) | Run `users list --no-fetch --json --limit 1` | Exit 0; JSON has `user_count` 1 and user U1 |
| TC-28 | Field selection in human output (`test_cli.py::test_show_users_fields_human`) | Run `users list --no-fetch --fields id,name` | Exit 0; output has `U1  alice` and not Alice Smith |
| TC-29 | Field selection in JSON (`test_cli.py::test_show_users_fields_json`) | Run `users list --no-fetch --json --fields id,real_name` | Exit 0; user object is exactly `{"id": "U1", "real_name": "Alice Smith"}` |
| TC-30 | Invalid field rejected (`test_cli.py::test_show_users_invalid_fields`) | Run `users list --no-fetch --fields bogus` | Exit 2 with `unknown field(s): bogus` |
| TC-31 | Thread render resolves user name (`test_cli.py::test_show_renders_user_name_when_cached`) | Fetch users, then `conversations get --no-fetch` | Output shows `] Alice Smith (alice)` and not the raw user id |
| TC-32 | Search render resolves user and channel names (`test_cli.py::test_search_renders_cached_user_and_channel_names`) | Fetch users and channels, then `conversations search --json` | Match reports `user_name` `Alice Smith (alice)` and `channel_name` `general` |
| TC-33 | Direct-message peer name in show (`test_cli.py::test_show_direct_channel_resolves_peer_name`) | Fetch users and channels, fetch the DM, then show it | Output shows `Channel Tom Rochette (tomzx)` and not `Channel D1` |
| TC-34 | Direct-message peer name in show JSON (`test_cli.py::test_show_direct_channel_json_resolves_peer_name`) | Same, with `--json` | JSON has `channel_name` `Tom Rochette (tomzx)` |
| TC-35 | Direct-message peer name in channel list (`test_cli.py::test_show_channels_labels_direct_channels`) | Fetch users and channels, then `channels list` | Output shows `D1  Tom Rochette (tomzx)  (direct)` |
| TC-36 | Direct-message peer name in search (`test_cli.py::test_search_direct_channel_hit_shows_peer_name`) | Fetch channels and users, then search | Output shows `[Tom Rochette (tomzx)]` and not `[D1]` |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-37 | Slack returns no user payload for a single fetch | `fetch_user` returns `None` and writes nothing (TC-3) |
| TC-38 | The same user is fetched twice | The row is replaced in place, with no duplicate (TC-4, TC-12) |
| TC-39 | Only some of a thread's participants are cached | Only the requested ids are resolved; others fall back to their id (TC-8) |
| TC-40 | A user has neither real name nor handle | The display name falls back to the user id (TC-9) |
| TC-41 | An unknown user id is requested with `--no-fetch` | The command reports `error: user U9 is not cached` and exits 1 (TC-22) |
| TC-42 | An unknown user id is fetched from Slack | The command reports `error: user U9 not found` and exits non-zero (TC-19) |

## Test Infrastructure

- `tests/test_cache.py` uses `FakeListClient`, an in-memory stand-in for `iter_users` and `get_user_info`, with a temporary SQLite database via `connect(tmp_path / "cache.db")`.
- `tests/test_cli.py` uses `FakeListClient`, `FakeMultiListClient`, and `DirectChannelClient`, and monkeypatches `cli._internal._client._build_client`, with `capsys` for stdout and stderr assertions and a temporary database.
- `tests/test_storage.py` uses a temporary SQLite database and the user CRUD, display-name, and status helpers.
- `tests/test_slack_api.py` drives the real `SlackClient` through a fake httpx transport and collects the async iterator.
- `tests/` runs under pytest with `testpaths=tests`; no network access is needed.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-01 | TC-1, TC-13, TC-14, TC-17 |
| FR-02 | TC-5, TC-6 |
| FR-03 | TC-4, TC-12 |
| FR-04 | TC-17, TC-20, TC-28 |
| FR-05 | TC-23, TC-24, TC-27, TC-29 |
| FR-06 | TC-21, TC-25 |
| FR-07 | TC-8, TC-9, TC-31 |
| FR-08 | TC-13, TC-14 |
| NFR-01 | TC-8, TC-31 |
| NFR-02 | TC-1, TC-4 (the processed, added, and total counts the command prints; no test asserts the stderr text itself) |
