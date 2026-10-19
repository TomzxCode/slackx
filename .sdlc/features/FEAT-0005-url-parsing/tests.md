---
title: "URL Parsing"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: URL Parsing

## Scope

This plan covers the permalink and argument parsing in `src/slackx/urls.py`
(`ThreadRef`, `_pts_to_ts`, `parse_thread_url`, `parse_channel_url`, `parse_channel_ts`,
`CHANNEL_PREFIXES`) and the CLI target resolution in
`src/slackx/cli/_internal/_refs.py` that consumes it.

In scope: root and reply permalinks, channel permalinks, direct message channel ids,
explicit channel and ts arguments, and the CLI target forms (permalink, channel id,
channel name and `#name`).

Out of scope: live Slack network calls, Slack deep links (`slack://`), enterprise
hostnames, and the user id or `@handle` branch of `_resolve_dm_channel` (no CLI test
exercises it). The stale CLI tests `test_fetch_channel_via_url`, `test_show_channel_via_url`,
and `test_resolve_ref_requires_url_or_channel_ts` are excluded: they reference the removed
`--url` flag and `_resolve_ref` symbol and currently fail.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Parse a thread root permalink into a ThreadRef (`test_parse_thread_root_permalink`) | `https://acme.slack.com/archives/C0123ABCDEF/p1700000000123456` | `ThreadRef("C0123ABCDEF", "1700000000.123456")` |
| TC-2 | A reply permalink uses the `thread_ts` query value as the root (`test_parse_reply_permalink_uses_thread_ts_query`) | `.../C0123ABCDEF/p1700000099654321?thread_ts=1700000000.123456&cid=...` | `ThreadRef("C0123ABCDEF", "1700000000.123456")` |
| TC-3 | A `D`-prefixed direct message channel id is accepted (`test_parse_dm_channel_id`) | `.../archives/D0123ABCDEF/p1700000000000001` | channel `D0123ABCDEF`, ts `1700000000.000001` |
| TC-4 | Malformed thread permalinks raise ValueError (`test_parse_thread_url_rejects_bad_inputs`) | non-slack host, `/messages/` path, `X` prefix, non-`p` ts | ValueError |
| TC-5 | A channel permalink returns its channel id (`test_parse_channel_url_returns_channel_id`) | `.../archives/D0123ABCDEF` | `"D0123ABCDEF"` |
| TC-6 | A thread permalink is not a channel permalink (`test_parse_channel_url_returns_none_for_thread_permalink`) | `.../archives/C0123ABCDEF/p1700000000123456` | None |
| TC-7 | Bad channel permalinks return None (`test_parse_channel_url_returns_none_for_bad_inputs`) | non-slack host, `/messages/`, `X` prefix, extra path segment | None |
| TC-8 | `parse_channel_ts` builds a ThreadRef (`test_parse_channel_ts_happy_path`) | channel `C0123ABCDEF`, ts `1700000000.123456` | `ThreadRef("C0123ABCDEF", "1700000000.123456")` |
| TC-9 | `parse_channel_ts` rejects bad inputs (`test_parse_channel_ts_rejects_bad_inputs`) | `X123`/ts, empty channel, `C123`/`1700000000`, `C123`/`not-a-ts` | ValueError |

## Integration Tests

Each test drives the CLI with a monkeypatched `_build_client` stub, so `_resolve_target`
runs against a controlled client and cache.

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-10 | A missing target exits non-zero (`test_fetch_channel_requires_url_or_channel_ts`) | No positional target | SystemExit |
| TC-11 | A channel id target shows that channel (`test_show_channel_with_name`) | Seeded channel `C1` named general | Output contains `general` |
| TC-12 | A direct channel id target resolves the peer name (`test_show_direct_channel_resolves_peer_name`) | Channel `D1` with peer `U9` cached | Output shows `Channel Tom Rochette (tomzx)`, not `Channel D1` |
| TC-13 | A `#`-prefixed channel name resolves (`test_show_channel_resolves_hash_prefixed_name`) | Channel `general` cached as `C1` | Output contains the `C1` message and `1 message(s)` |
| TC-14 | Fetching by channel name resolves it to the id (`test_fetch_channel_resolves_name`) | Channel `general` cached as `C1` | Summary reports `for C1` |
| TC-15 | A name plus `--ts` resolves the name before fetching the thread (`test_fetch_thread_resolves_channel_name`) | Channel `general` cached as `C1` | Thread fetch receives channel `C1` |
| TC-16 | An unresolved channel name errors (`test_show_channel_unresolved_name_errors`) | Empty channel cache, target `#nope` | Exit code 1, stderr contains `could not resolve` and `nope` |
| TC-17 | A channel target marks the latest read pointer (`test_read_mark_channel_defaults_to_latest`) | Seeded entities in the cache | Read marker for `web` with ts `1700000000.000100` |
| TC-18 | `--ts` distinguishes the thread pointer from the channel pointer (`test_read_mark_thread_scope`) | Seeded entities in the cache | Marker for `web` with thread_ts `1700000000.000100` |

## End-to-End Tests

The CLI tests run the full `cli.main` path (parse, resolve, fetch through a stub client,
cache, render). No test runs the built-in fake Slack server through the CLI for this feature.

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-19 | Fetch a thread from a positional permalink (`test_fetch_with_url`) | Run `conversations fetch <thread permalink> --db <tmp>` | Exit 0, thread replies fetched once |
| TC-20 | Show a channel from a bare name (`test_show_channel_resolves_bare_name`) | Fetch channels, then `conversations get general --db <tmp>` | Exit 0, output contains the `C1` message and `1 message(s)` |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-21 | Reply permalink carrying `?thread_ts=` (`test_parse_reply_permalink_uses_thread_ts_query`) | Returns the query thread root ts, not the path reply ts |
| TC-22 | Non-slack URL or wrong path (`test_parse_thread_url_rejects_bad_inputs`, `test_parse_channel_url_returns_none_for_bad_inputs`) | ValueError from `parse_thread_url`, None from `parse_channel_url` |
| TC-23 | Malformed permalink ts without the `p` prefix (`test_parse_thread_url_rejects_bad_inputs`) | ValueError |
| TC-24 | Channel prefix not in `C`/`G`/`D` (`test_parse_thread_url_rejects_bad_inputs`, `test_parse_channel_ts_rejects_bad_inputs`) | ValueError |
| TC-25 | `--ts` without a dot or non-numeric (`test_parse_channel_ts_rejects_bad_inputs`) | ValueError |
| TC-26 | Empty channel with a valid ts (`test_parse_channel_ts_rejects_bad_inputs`) | ValueError |
| TC-27 | Channel permalink with an extra segment or `/messages/` path (`test_parse_channel_url_returns_none_for_bad_inputs`) | None |
| TC-28 | Thread permalink passed to `parse_channel_url` (`test_parse_channel_url_returns_none_for_thread_permalink`) | None |
| TC-29 | Unresolved channel name through the CLI (`test_show_channel_unresolved_name_errors`) | Exit code 1 with a `could not resolve` error |

## Test Infrastructure

- Framework: pytest, configured with `testpaths = tests` and `addopts = -ra`.
- Unit tests live in `tests/test_urls.py` and import from `slackx.urls`; they need no fixtures.
- CLI tests live in `tests/test_cli.py` and drive `slackx.cli.main` directly.
- The Slack client is stubbed by monkeypatching `slackx.cli._internal._client._build_client` with async stub clients (`FakeChannelClient`, `FakeThreadClient`, `EmptyClient`, `DirectChannelClient`) that implement `iter_thread_replies`, `iter_channels`, `iter_channel_history`, and `aclose`.
- `tmp_path` supplies an isolated SQLite cache per test; `capsys` captures stdout and stderr for assertions.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-01 | TC-1, TC-19 |
| FR-02 | TC-1, TC-3 |
| FR-03 | TC-2, TC-21 |
| FR-04 | TC-3, TC-4, TC-5, TC-24 |
| FR-05 | TC-8, TC-19, TC-20 |
| FR-06 | TC-4, TC-7, TC-9, TC-16, TC-22, TC-23, TC-24, TC-25 |
| FR-07 | TC-8, TC-11, TC-12, TC-17 |
| FR-08 | TC-9, TC-25 |
| NFR-01 | TC-4, TC-9, TC-16, TC-29 |
