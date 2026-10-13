---
title: "Channel Polling"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Requirements: Channel Polling

## Overview

The `slackx conversations poll` command runs a long-lived loop that fetches new messages from one or more channels on a fixed interval.
Each cycle resolves the requested channels, fetches their recent history into the local SQLite cache, and waits until the interval has elapsed before starting the next cycle.
The loop is meant to run in the background and stop cleanly when the user presses `Ctrl+C`.
This document reverse-engineers the already-implemented behavior; it records what the code does today rather than requesting new work.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| CLI user | Wants a single command that keeps the local cache current without re-typing fetch commands |
| CLI user running a long session | Wants channel fetches to run concurrently and to stop cleanly on `Ctrl+C` |
| Developer | Needs a repeatable way to keep a workspace cache warm for the web UI and search |
| Operator of a large workspace | Wants concurrent fetches to respect Slack rate limits instead of tripping HTTP 429 |

## Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall accept a `--channels` value containing a comma-separated list of channel ids, bare names, or `#`-prefixed names |
| FR-2 | Must | The system shall resolve channel names against the cached channels and exit 1 with an error when a name cannot be resolved |
| FR-3 | Must | The system shall require at least one channel and exit 1 with an error when `--channels` is empty |
| FR-4 | Must | The system shall poll the resolved channels repeatedly until the user interrupts it |
| FR-5 | Must | The system shall wait `--interval` (default `5m`) between cycles, counting the cycle's own duration toward the interval |
| FR-6 | Must | The system shall reject `--interval all` with an error and exit 1, because a polling interval must be finite |
| FR-7 | Must | The system shall fetch each polled channel's recent messages each cycle via `fetch_channel_messages` and write them to the cache |
| FR-8 | Must | The system shall limit the lookback per cycle with `--last` (default `5m`) by converting the duration to an epoch-seconds `oldest` value, where `all` means no lower bound |
| FR-9 | Must | The system shall bound the number of concurrent channel fetches with `--concurrency` (default 3) using an `asyncio.Semaphore` |
| FR-10 | Should | The system shall fetch all thread replies for each channel when `--full-threads` is passed |
| FR-11 | Must | The system shall print a per-cycle summary to stderr and continue the cycle when an individual channel fetch fails |
| FR-12 | Should | The system shall emit a per-cycle JSON summary to stdout when `--json` is passed |
| FR-13 | Must | The system shall stop cleanly on `Ctrl+C`, log the interruption, and print the number of completed cycles |
| FR-14 | Must | The system shall throttle proactively from `X-RateLimit-*` headers through a shared `RateLimitState` to avoid HTTP 429 responses |
| FR-15 | Should | The system shall accept the shared `--db`, `--workspace`, `--api-base-url`, and `--log-level` options |

## Non-Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Reliability | A single channel's failure shall not abort the cycle or stop the loop |
| NFR-2 | Should | Performance | The system shall fetch channels concurrently, bounded by the configured semaphore |
| NFR-3 | Must | Efficiency | The loop shall reuse one `httpx.AsyncClient` and one database path resolution across all cycles |
| NFR-4 | Should | Reliability | The system shall wait for the rate-limit window to reset when the bucket is nearly exhausted, reducing HTTP 429 responses |
| NFR-5 | Should | Observability | The loop shall log cycle start, channel completion, channel error, sleep, and interruption with structlog |

## Constraints

- The loop runs until interrupted; there is no maximum-cycle or run-once option.
- `--interval` must be a finite duration, so `all` is rejected while `--last` accepts `all`.
- Channel names are resolved against the cached channels, so unknown names error until `slackx channels fetch` has populated them.
- One SQLite database exists per workspace, and each channel fetch opens and closes its connection through `_open_db_at`.
- The loop reuses the existing `fetch_channel_messages` path and its `ChannelFetchResult`; no new storage or schema is introduced.
- The command returns exit code 0 after a clean interrupt and exit code 1 for input errors.

## Acceptance Criteria

Every FR and NFR shall have at least one acceptance criterion.

Order criteria by FRs first (sorted by ID), then NFRs (sorted by ID).

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Accept a mixed channel list
      Given the cached channels contain general and random
      When the user runs "conversations poll --channels #general,random,C3"
      Then the command polls C1 for general, C2 for random, and C3 directly
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Reject an unresolvable channel name
      Given the cached channels do not contain nope
      When the user runs "conversations poll --channels #nope"
      Then the command prints "could not resolve" to stderr and exits 1
    ```
- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Reject an empty channel list
      When the user runs "conversations poll --channels ''"
      Then the command exits 1 without starting a poll cycle
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Keep polling until interrupted
      Given a valid channel list
      When the poll loop starts
      Then it runs cycle 1, cycle 2, and further cycles until the user interrupts it
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Wait between cycles
      Given the interval is 1s and a cycle takes less than 1s
      When the cycle completes
      Then the loop sleeps for the remaining time before the next cycle
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Reject an infinite interval
      When the user runs "conversations poll --channels C1 --interval all"
      Then the command prints "error: --interval must be a finite duration (not 'all')" and exits 1
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Fetch and store each channel each cycle
      Given a valid channel list and a fake Slack API returning one message per channel
      When the poll loop runs one cycle
      Then each channel's messages are written to the cache
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Convert the lookback to an oldest timestamp
      Given the user passes "--last 5m"
      When a cycle starts
      Then the loop passes an epoch-seconds oldest value of now minus 5 minutes to the channel fetch
    ```

    ```gherkin
    @FR-8
    Scenario: Fetch full history when last is all
      Given the user passes "--last all"
      When a cycle starts
      Then the loop passes oldest=None to the channel fetch
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Bound concurrent channel fetches
      Given the user passes "--concurrency 1" with two channels
      When a cycle runs
      Then no more than one channel fetch runs at a time
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Expand thread replies
      Given the user passes --full-threads
      When a cycle fetches a channel
      Then fetch_channel_messages is called with full_threads enabled
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Continue after a channel fetch fails
      Given one channel raises during fetch and another succeeds
      When a cycle runs
      Then the cycle logs the error, reports the failing channel with an error marker, and still fetches the healthy channel
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: Emit a JSON cycle summary
      Given the user passes --json
      When a cycle completes
      Then a JSON object with cycle, elapsed_seconds, and channels is written to stdout
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Stop cleanly on Ctrl+C
      Given the poll loop is running
      When the user presses Ctrl+C
      Then the loop logs the interruption and prints "poll stopped after N cycle(s)" to stderr
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: Throttle from rate-limit headers
      Given the rate-limit bucket is nearly exhausted
      When a request completes with X-RateLimit headers
      Then the loop waits for the reset window before sending the next request
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: Honor the shared options
      When the user runs "conversations poll --channels C1 --db PATH --api-base-url URL --log-level debug"
      Then the command polled through the given database, API base URL, and log level
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Isolate a channel failure
      Given one of two channels raises on every fetch
      When the loop runs several cycles
      Then the healthy channel keeps being fetched in every cycle
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Fetch concurrently within the bound
      Given three channels and a concurrency of 3
      When a cycle runs
      Then the three channel fetches overlap in time and stay within the semaphore bound
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Reuse the HTTP client and database path
      Given the poll loop has started
      When it runs multiple cycles
      Then one AsyncClient and one resolved database path are used for the whole run
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Wait for the rate-limit reset
      Given the remaining rate-limit count is 2 or lower with a future reset time
      When the loop is about to send a request
      Then it sleeps until the reset time before sending
    ```

- [ ] **NFR-5**

    ```gherkin
    @NFR-5
    Scenario: Log the loop lifecycle
      Given the poll loop runs a cycle and then is interrupted
      When the cycle completes and the interrupt arrives
      Then poll_start, poll_channel_done, poll_sleep, and poll_interrupted events are logged
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should a run-once or `--max-cycles` option be added so the command can be used from cron without an external timeout?
2. Should the poll loop update read markers or emit notifications when new messages arrive?
3. Should consecutive failures back off instead of retrying every cycle at the fixed interval?
