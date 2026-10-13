---
title: "Cache Management"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Requirements: Cache Management

## Overview

The cache grows as threads, messages, channels, users, and read markers are fetched from Slack, and a user needs a way to see how much is stored and to remove it selectively.
This feature provides the `slackx cache status` command, which reports counts and last update times for the local cache database, and the `slackx cache clear` command, which deletes all cached data or one entity at a time.
Both commands operate directly on the local SQLite database and never call Slack.
This document was reverse-engineered from the implemented commands in `src/slack_cached/cli/commands/cache_status.py`, `src/slack_cached/cli/commands/cache_clear.py`, and the storage helpers in `src/slack_cached/storage.py`.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| CLI user | Needs to check what is cached and reclaim disk space by clearing stale data |
| Web UI consumer | Depends on the same storage helpers for cache counts |
| Developer | Needs selective clearing to reset one entity without discarding the rest |

## Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall report the count of cached channels, users, threads, messages, and read markers in the cache database |
| FR-2 | Must | The system shall report the last update time for channels, users, and threads, or no time when the table is empty |
| FR-3 | Must | The system shall delete cached data for the selected target of `all`, `messages`, `channels`, `users`, or `read`, defaulting to `all` |
| FR-4 | Must | The system shall delete the thread rows that belong to messages when messages are cleared, so the threads are refetched on next use |
| FR-5 | Must | The system shall ask for confirmation before deleting unless the `--yes` flag is passed |
| FR-6 | Must | The system shall refuse to delete anything and exit non-zero when confirmation is required but standard input is not an interactive terminal |
| FR-7 | Should | The system shall print the number of cleared messages, threads, channels, users, and read markers after a successful clear |
| FR-8 | Should | The system shall support `--json` and `--jsonl` machine-readable output for the status command |

## Non-Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Safety | The system shall never delete cached data without an explicit confirmation, given by an interactive yes or by `--yes` |
| NFR-2 | Must | Security | The system shall read and modify the cache database directly and never call the Slack API |
| NFR-3 | Should | Usability | The system shall render the status report in a human-readable form by default |
| NFR-4 | Should | Performance | The system shall answer status and clear requests as local database operations without network round trips |

## Constraints

- Both commands act on the SQLite database resolved from `--db` or the per-workspace default path.
- The clear target is limited to `all`, `messages`, `channels`, `users`, and `read`.
- The confirmation prompt only runs when standard input is an interactive terminal.

## Acceptance Criteria

Every FR and NFR shall have at least one acceptance criterion.

Order criteria by FRs first (sorted by ID), then NFRs (sorted by ID).

Acceptance criteria verify how a requirement is proven done, they do not restate it.
Write concrete, scenario-based criteria (happy path, edge cases and error states where applicable).
Write each criterion as a fenced `gherkin` block with a tag matching its requirement ID, so the criteria are parseable and later executable via BDD tooling (pytest-bdd, cucumber).
Multiple scenarios per requirement are allowed; tag each with the requirement ID.

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Status reports counts for a populated cache
      Given a cache database with one channel, one user, one thread, and one message
      When the user runs `slackx cache status`
      Then the output shows channel count 1, user count 1, thread count 1, and message count 1
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Status reports update times for a populated cache
      Given a cache database with a channel, a user, and a thread each carrying a fetch time
      When the user runs `slackx cache status`
      Then the output shows the last update time for channels, users, and threads
    ```

    ```gherkin
    @FR-2
    Scenario: Status reports no update time for an empty cache
      Given an empty cache database
      When the user runs `slackx cache status`
      Then the channel, user, and thread update times are empty
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Clear defaults to every entity
      Given a cache database with messages, channels, and users
      When the user runs `slackx cache clear --yes`
      Then messages, threads, channels, and users are all removed
    ```

    ```gherkin
    @FR-3
    Scenario: Clear a single target keeps the others
      Given a cache database with messages, channels, and users
      When the user runs `slackx cache clear channels --yes`
      Then channels are removed and messages and users remain
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Clearing messages drops the thread metadata
      Given a cache database with a cached thread and its message
      When the user runs `slackx cache clear messages --yes`
      Then the thread state for that thread is gone so it is refetched next time
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Clear proceeds without a prompt when the yes flag is passed
      Given a cache database with cached data
      When the user runs `slackx cache clear --yes`
      Then the command deletes the data without asking for confirmation
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Clear refuses on a non-interactive terminal without the yes flag
      Given a cache database with cached data and standard input that is not a terminal
      When the user runs `slackx cache clear` without `--yes`
      Then the command exits with code 1, prints that `--yes` is required, and deletes nothing
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Clear prints the cleared counts
      Given a cache database with one message, thread, channel, and user
      When the user runs `slackx cache clear --yes`
      Then the output reports messages=1, threads=1, channels=1, and users=1
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Status supports JSON output
      Given a cache database with cached data
      When the user runs `slackx cache status --json`
      Then the output is a JSON object with the count and update-time fields
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Clear deletes nothing without confirmation
      Given a cache database with cached data and no interactive terminal
      When the user runs `slackx cache clear` without `--yes`
      Then the cached counts are unchanged
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Status and clear stay local
      Given a cache database and no reachable Slack API
      When the user runs `slackx cache status` or `slackx cache clear --yes`
      Then both commands complete without any Slack API call
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Status is human-readable by default
      Given a cache database with cached data
      When the user runs `slackx cache status` without a format flag
      Then the output is a human-readable status report rather than JSON
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Status runs as a local operation
      Given a cache database with cached data
      When the user runs `slackx cache status`
      Then the command completes without a network round trip
    ```

## Conflicts

<!-- Identified and populated by /review-requirements: pairs or groups of requirements that cannot all be satisfied at once. Reconcile before approval, or promote to an open question. -->

None identified yet.

## Open Questions

1. None.
