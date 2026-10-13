---
title: "Read markers (last-read tracking)"
status: done
session_link: http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ
---

# Requirements: Read markers (last-read tracking)

## Overview

slackx caches channels and threads in one SQLite database per workspace.
When several programs share that cache (a web UI, a poll watcher, an ad-hoc script), each needs to remember how far it has read without overwriting the others.
The read markers feature stores per-consumer last-read pointers, exposes them through the `slackx conversations read` command group and the `serve` HTTP API, and persists them in the cache database so they survive restarts.
`slackx conversations show` also advances the pointer for the shown channel or thread after printing, so showing a conversation to a consumer is reading it.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| CLI user | Wants to record and inspect how far a consumer has read in a channel or thread |
| Cache consumer (web UI, poll watcher, script) | Needs an independent last-read position over a shared cache |
| Operator | Wants to inspect and clear pointers without touching cached messages |

## Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall record a last-read pointer for a reader, a channel, and an optional thread ts, keyed by (reader, channel, thread_ts) |
| FR-2 | Must | The system shall treat a pointer with no thread ts as the channel-level pointer and a pointer with a thread ts as that thread's pointer, storing them as separate rows |
| FR-3 | Must | The system shall keep each reader's pointers independent, so one reader never overwrites another's |
| FR-4 | Must | The system shall default a stored timestamp to the newest cached message in scope when no explicit value is given |
| FR-5 | Should | The system shall store an explicit timestamp when one is provided |
| FR-6 | Must | The `slackx conversations read mark` command shall exit nonzero when no cached messages exist in scope and no explicit timestamp is given |
| FR-7 | Must | The `slackx conversations read mark` command shall reject an empty reader |
| FR-8 | Must | The `slackx conversations read show` command shall list stored pointers, optionally filtered by reader and by channel, human-readable by default with JSON and JSONL options |
| FR-9 | Must | The `slackx conversations read clear` command shall delete one thread pointer, every pointer for a channel, or every pointer for a reader, based on the arguments given |
| FR-10 | Must | The `slackx conversations read clear` command shall reject an empty reader and a thread ts given without a channel |
| FR-11 | Must | The HTTP API shall list pointers via GET /api/read, create or advance a pointer via PUT /api/read, and delete pointers via the DELETE routes |
| FR-12 | Must | The HTTP API shall return 404 when a PUT finds no cached messages in scope and 422 when the reader is blank |
| FR-13 | Should | The `slackx cache clear read` command shall delete every stored pointer while leaving messages, threads, users, and channels in place |
| FR-14 | Should | The `slackx conversations show` command shall advance the last-read pointer for the shown channel or thread for the chosen reader (default `default`) after printing, and leave pointers unchanged when nothing is shown |

## Non-Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Reliability | Writes shall upsert on the primary key, so re-marking a scope updates the stored timestamp instead of adding a duplicate row |
| NFR-2 | Must | Data integrity | The channel-level marker shall be stored with an empty-string sentinel in thread_ts and returned to callers as null |
| NFR-3 | Should | Usability | Command output shall be human-readable by default and machine-readable with --json or --jsonl |
| NFR-4 | Should | Performance | Pointer lookup and listing shall use the read_markers primary key and the idx_read_markers_reader index |

## Constraints

- Pointers live in the same cache database as messages, so they are per workspace and survive restarts.
- The storage layer owns no transactions; callers wrap writes in `transaction(conn)`.
- The channel-level pointer is distinguished from a thread pointer by an empty-string sentinel in the thread_ts column.
- Mark, show, and clear operate on the local cache and do not fetch from Slack.

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
    Scenario: Record a pointer for a consumer
      Given a cache with messages in channel C1
      When the user runs "slackx conversations read mark C1 --reader web"
      Then a read marker row exists for reader web in channel C1
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Channel and thread pointers are separate rows
      Given a cache with messages in channel C1
      When the user marks the channel pointer and then the thread pointer for ts 1700000000.000100
      Then two read marker rows exist for that reader, one with a null thread ts and one with that thread ts
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Readers do not overwrite each other
      Given a cache with messages in channel C1
      When the web reader marks the channel and the poll reader marks the same channel
      Then each reader has its own channel pointer with no shared row
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Marking without an explicit value uses the newest cached message
      Given a cache whose newest cached message in channel C1 has ts 1700000000.000100
      When the user marks channel C1 without --last-read
      Then the stored last-read ts is 1700000000.000100
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: An explicit value is stored as given
      Given a cache with messages in channel C1
      When the user marks channel C1 with --last-read 1700000000.000050
      Then the stored last-read ts is 1700000000.000050
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Marking a scope with no cached messages fails
      Given a cache with no cached messages in channel CNOPE
      When the user runs "slackx conversations read mark CNOPE --reader web"
      Then the command exits with code 1 and reports that no messages are cached
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Empty reader is rejected
      Given a cache with messages in channel C1
      When the user runs "slackx conversations read mark C1 --reader ' '"
      Then the command exits with code 2 and reports that the reader must not be empty
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Showing pointers filtered by reader
      Given markers for readers web and poll in channel C1
      When the user runs "slackx conversations read show --reader web --json"
      Then the output contains only the web marker and reports a read count of 1
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Clearing a single thread pointer
      Given a channel pointer and a thread pointer for reader web in channel C1
      When the user runs "slackx conversations read clear --reader web --channel C1 --ts 1700000000.000100"
      Then the thread pointer is removed and the channel pointer remains
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Thread ts without a channel is rejected
      Given a configured workspace
      When the user runs "slackx conversations read clear --reader web --ts 1700000000.000100"
      Then the command exits with code 2 and reports that --ts requires --channel
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Creating a pointer over HTTP
      Given a running serve instance backed by a cache with messages in channel C1
      When the client sends PUT /api/read with reader web and channel C1
      Then the response contains a marker for channel C1 and a later GET /api/read lists it
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: HTTP error states
      Given a running serve instance backed by a cache
      When the client PUTs to /api/read for a channel with no cached messages and PUTs a blank reader
      Then the first response is 404 and the second response is 422
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Clearing read markers leaves other cache data alone
      Given a cache with one read marker, one message, and other cached entities
      When the user runs "slackx cache clear read --yes"
      Then the read marker count is zero and the message count is unchanged
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: Showing a channel advances its pointer
      Given a cache with messages in channel C1
      When the user runs "slackx conversations show C1 --reader web"
      Then the printed output is unchanged and the web channel pointer is advanced to the newest cached message
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Re-marking a scope updates the row
      Given a channel pointer for reader web with one timestamp
      When the user marks the same channel again with a newer timestamp
      Then the marker count stays at 1 and the stored timestamp is the newer value
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: The channel-level sentinel round-trips as null
      Given the channel-level pointer for reader web in channel C1
      When a caller reads the marker back through the API or CLI
      Then the returned thread ts is null
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Human and machine output
      Given a stored marker for reader web
      When the user runs "slackx conversations read show" then "slackx conversations read show --json"
      Then the first output is human-readable text and the second is valid JSON
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Listing uses the reader index
      Given a cache with many markers across readers and channels
      When the user lists markers for one reader
      Then the query returns the matching rows ordered by reader, channel, and scope
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should readers be length-limited or validated beyond the non-empty check?
2. Should the HTTP API require authentication before it accepts pointer writes?
