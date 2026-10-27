---
title: "Cache Management"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Cache Management

## Scope

This plan covers the cache status and cache clear commands and the storage helpers they call (`db_status`, `clear_cache`, and the count helpers).
It verifies counts and update times, per-target clearing, thread cleanup on message clear, the confirmation path, and the non-interactive refusal.
It does not cover fetching from Slack or the web UI's use of the same helpers.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | `db_status` on an empty database reports zero counts and no update times | Fresh database | All counts are 0 and all update times are None (test_storage.py, `test_db_status_empty`) |
| TC-2 | `db_status` reports counts and newest update times | One channel, two users, one thread, one message with set fetch times | Counts are 1/2/1/1 and the update times match the seeded values (test_storage.py, `test_db_status_counts_and_last_updates`) |
| TC-3 | `clear_cache` on messages keeps read markers | A read marker plus a message clear | Read marker count stays 1 after messages clear (test_storage.py, `test_clear_cache_read_markers`) |
| TC-4 | `clear_cache` on read markers removes them | A read marker plus a read-marker clear | Cleared read marker count is 1 and the table is empty (test_storage.py, `test_clear_cache_read_markers`) |
| TC-4b | `workspace_name_from_db_path` recognizes the per-workspace layout | A per-workspace, a legacy, and a custom path | Returns the workspace name, `None`, and `None` respectively (test_workspace.py, `TestWorkspaceDbPath`) |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-5 | `cache status` prints counts and update times | Seeded database with a channel, user, thread, and message | Exit 0 and output shows 1 channel, 1 user, 1 thread, 1 message, and a dated update (test_cli.py, `test_status_human`) |
| TC-6 | `cache status --json` emits the counts and update times | Seeded database | Exit 0 and JSON has the expected count and update-time fields (test_cli.py, `test_status_json`) |
| TC-7 | `cache status --jsonl` emits one compact JSON line | Empty database | Exit 0 and a single JSON line with zero counts (test_cli.py, `test_status_jsonl`) |
| TC-7b | `cache status` reports the resolved workspace and database path | Per-workspace database for "acme" | Exit 0 and output shows `Workspace: acme` and the database path (test_cli.py, `test_status_reports_workspace`) |
| TC-7c | `cache status` omits the workspace for a custom `--db` | Database at a custom path | Exit 0, output shows the database path, and `workspace` is null in JSON (test_cli.py, `test_status_human`, `test_status_json`) |
| TC-8 | `cache clear` defaults to every entity | Seeded database | Exit 0, output reports messages=1 threads=1 channels=1 users=1, and every count drops to 0 (test_cli.py, `test_clear_defaults_to_everything`) |
| TC-9 | `cache clear messages` clears messages and threads only | Seeded database | Exit 0 and message and thread counts drop to 0 while channels and users stay 1 (test_cli.py, `test_clear_messages_also_clears_threads_and_keeps_the_rest`) |
| TC-10 | `cache clear channels` keeps messages and users | Seeded database | Exit 0 and channel count drops to 0 while messages, threads, and users stay (test_cli.py, `test_clear_channels_keeps_messages_and_users`) |
| TC-11 | `cache clear users` keeps messages and channels | Seeded database | Exit 0 and user count drops to 0 while messages, threads, and channels stay (test_cli.py, `test_clear_users_keeps_messages_and_channels`) |
| TC-12 | `cache clear read` clears only read markers | Seeded database with a read marker | Exit 0 and read marker count drops to 0 while messages stay 1 (test_cli.py, `test_clear_read_markers_target`) |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-13 | Clearing messages reopens the thread for refetch | Seed a thread, run `cache clear messages --yes`, then read the thread state | Thread state is None so the next show refetches (test_cli.py, `test_clear_messages_reopens_thread_for_refetch`) |
| TC-14 | Status reflects the cache after a clear | Seed the database, run `cache clear --yes`, then run `cache status` | Status reports zero counts after the clear |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-15 | Clear without `--yes` on a non-interactive terminal | Exit 1, print that `--yes` is required, and delete nothing (test_cli.py, `test_clear_requires_confirmation_without_yes`) |
| TC-16 | Clear read markers leaves other data | Read markers are removed while messages, threads, and channels stay (test_cli.py, `test_clear_read_markers_target`) |
| TC-17 | Clear all removes every entity | Messages, threads, channels, and users are all removed and counts drop to 0 (test_cli.py, `test_clear_defaults_to_everything`) |

## Test Infrastructure

- pytest with the repository's tmp_path fixture for a fresh database per test.
- CLI tests drive the commands through `cli.main` and capture output with capsys.
- A shared `_seed_all_entities` helper populates a channel, user, thread, and message for the clear tests.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-1, TC-2, TC-5, TC-6 |
| FR-2 | TC-2, TC-5, TC-6, TC-7 |
| FR-3 | TC-8, TC-9, TC-10, TC-11, TC-12, TC-17 |
| FR-4 | TC-9, TC-13 |
| FR-5 | TC-8, TC-15 |
| FR-6 | TC-15 |
| FR-7 | TC-8 |
| FR-8 | TC-6, TC-7 |
| FR-9 | TC-7b, TC-7c |
| NFR-1 | TC-15 |
| NFR-2 | TC-5, TC-15 |
| NFR-3 | TC-5 |
| NFR-4 | TC-5, TC-8 |
