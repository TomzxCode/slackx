---
title: "Channel Polling"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Channel Polling

## Scope

This plan covers the `slackx conversations poll` command and its `_poll_loop` behavior.
It covers argument validation, channel name resolution, single and multiple cycles, JSON output, and per-channel error isolation.
It does not cover the rate-limit waiting path, the `Ctrl+C` path, or real network traffic, none of which have dedicated tests today.
The tests live in `tests/test_cli.py` and exercise the command end to end through `cli.main`.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Empty `--channels` is rejected (`test_poll_requires_channels`) | `--channels ""` | Exit code 1, no cycle runs |
| TC-2 | `--interval all` is rejected (`test_poll_rejects_interval_all`) | `--channels C1 --interval all` | Exit code 1 |
| TC-3 | Bare and `#`-prefixed names resolve via the cached channels (`test_poll_resolves_channel_names`) | `--channels "#general,random,C3"` after seeding C1=general, C2=random | Polled channels are C1, C2, C3 |
| TC-4 | An unresolvable name errors (`test_poll_unresolved_channel_name_errors`) | `--channels "#nope"` with empty channel cache | Exit code 1, stderr contains "could not resolve" and "nope" |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-5 | One cycle fetches every channel (`test_poll_single_cycle`) | Two channels seeded with one message each | Exit code 0, stderr has "polling 2 channel(s)", "cycle 1:", "poll stopped after 1 cycle(s)" |
| TC-6 | JSON per-cycle summary (`test_poll_json_output`) | One channel, one message, `--json` | stdout JSON has cycle 1, one channel entry for C1 with fetched == 1 |
| TC-7 | One failing channel does not stop the cycle (`test_poll_handles_channel_error`) | Channels C_BAD (raises) and C_OK (returns one message), `--json` | Exit code 0, one channel entry has an error, another has fetched == 1 |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-8 | Multiple cycles run before stopping (`test_poll_multiple_cycles`) | Run `conversations poll --channels C1 --interval 1s --last 1m` with the fake sleep stopping after 3 cycles | Exit code 0, stderr has "cycle 3:" and "poll stopped after 3 cycle(s)" |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-9 | A channel fetch raises mid-cycle (covered by TC-7) | The exception is logged as `poll_channel_error` and returned as `{"channel", "error": True}`; the other channels still complete |
| TC-10 | A cycle takes longer than `--interval` | `sleep_seconds` floors at 0, so the next cycle starts immediately |
| TC-11 | `--last all` is passed | `_oldest_ts_from_last` returns None, so the fetch has no lower bound and reads the full history |
| TC-12 | The user presses `Ctrl+C` during a sleep or fetch | `KeyboardInterrupt` or `CancelledError` is caught, logged as `poll_interrupted`, and "poll stopped after N cycle(s)" is printed |
| TC-13 | A `--channels` value made only of separators (for example ",") | Entries strip to empty, the command prints "error: --channels must contain at least one channel", and exits 1 |

## Test Infrastructure

- `FakeAsyncPollClient` in `tests/test_cli.py` is an async stub Slack client that records the `(channel, oldest)` calls and yields per-channel messages.
- `_patch_poll(monkeypatch, fake_client_cls, cycle_limit)` patches `asyncio.sleep` (raising `CancelledError` after `cycle_limit` calls), `httpx.AsyncClient`, and `slackx.slack_api.SlackClient`.
- `load_credentials` is monkeypatched to return a fixed test credential.
- Tests use `tmp_path` for the cache database and `capsys` to read stderr and stdout.
- `test_poll_resolves_channel_names` seeds the channel cache by running `channels fetch` with a stub `iter_channels` client before polling.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-3, TC-5 |
| FR-2 | TC-4 |
| FR-3 | TC-1 |
| FR-4 | TC-5, TC-8 |
| FR-5 | TC-8 |
| FR-6 | TC-2 |
| FR-7 | TC-5, TC-6 |
| FR-8 | TC-5, TC-6 |
| FR-9 | TC-5 |
| FR-10 | None (no dedicated test) |
| FR-11 | TC-7 |
| FR-12 | TC-3, TC-6 |
| FR-13 | None (no dedicated test) |
| FR-14 | None (no dedicated test) |
| FR-15 | TC-5 |
| NFR-1 | TC-7 |
| NFR-2 | TC-5 (indirectly) |
| NFR-3 | TC-7, TC-8 |
| NFR-4 | None (no dedicated test) |
| NFR-5 | TC-5, TC-6, TC-7 |
