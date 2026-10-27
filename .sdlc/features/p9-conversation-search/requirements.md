---
title: "Conversation Search"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Requirements: Conversation Search

## Overview

Conversation search lets a user run a Slack search query from the command line, cache every matched message under its own thread, and print the matches.
It wraps Slack's `search.messages` endpoint, so queries use the same syntax as the Slack search box.
Because search is a live operation, every run calls the API; caching matched messages makes them available later through `conversations get` without searching again.
This feature was reverse-engineered from already implemented code during `/sync-sdlc`; the artifacts below document existing behavior.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| CLI user | Wants to find messages by keyword and keep them locally for later reading |
| Developer | Needs search results routed into the same thread cache that `conversations get` and the web UI read |
| Web UI user | Reads cached matches through the local full-text search in the served SPA |

## Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall accept a search query argument on `conversations search` and return messages matching it from Slack's `search.messages` endpoint |
| FR-2 | Must | The system shall cache every matched message in the local SQLite cache under its `(channel, thread_ts)` |
| FR-3 | Must | The system shall normalize the `channel` field of each `search.messages` match from an object to a bare channel id |
| FR-4 | Must | The system shall resolve the thread root of a reply match that lacks `thread_ts` from the `thread_ts` query parameter of the match permalink |
| FR-5 | Must | The system shall page through `search.messages` with page-based pagination and stop at the reported `page_count`, on an empty page, or on a repeated page number |
| FR-6 | Must | The system shall print a summary to stderr with the match count and the thread and message breakdown into existing and new items |
| FR-7 | Must | The system shall support `--api-base-url` so the search can point at a non-default Slack API server |
| FR-8 | Should | When `--full-threads` is passed, the system shall fetch all replies for every distinct matched thread via `conversations.replies` |
| FR-9 | Should | The system shall accept `--limit` to cap the total matches fetched, defaulting to 200, where a non-positive value means no cap |
| FR-10 | Should | The system shall accept `--count` to set the maximum matches requested per page, defaulting to 20 |
| FR-11 | Should | The system shall accept `--sort` (`score` or `timestamp`) and `--sort-dir` (`asc` or `desc`) to control match ordering |
| FR-12 | Should | The system shall emit match output as human-readable text by default, as JSON with `--json`, and as a single JSON line with `--jsonl` |
| FR-13 | Should | The system shall accept `--fields` to choose and order emitted fields, and shall reject an unknown field with a non-zero exit code |
| FR-14 | Should | The system shall render cached user display names and channel names for matches, including the peer name for a match in a direct channel |
| FR-15 | May | In `--full-threads` mode the system shall not cache the search match directly, so that endpoint payload drift between `search.messages` and `conversations.replies` does not oscillate the cache, and shall fall back to the match when replies return nothing |

## Non-Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Reliability | The `search.messages` pager shall terminate on an empty page, on a `page` above `page_count`, and on a repeated page number, so a malformed response cannot loop forever |
| NFR-2 | Should | Performance | With `--full-threads`, the system shall fetch the distinct matched threads concurrently and commit each thread in its own transaction |
| NFR-3 | Should | Reliability | Search calls shall go through the shared Slack client that honors `Retry-After` backoff and proactive rate limit throttling |
| NFR-4 | Should | Robustness | The local full-text search shall defuse non-term and operator-only queries and shall return no results rather than raise when the FTS5 index is unavailable |
| NFR-5 | Should | Reliability | Re-running an unchanged search shall report zero new threads and zero new messages, even when the two endpoints decorate the same message differently |

## Constraints

- `search.messages` uses page-based pagination (page N of page_count), unlike the cursor-based pagination used by the list endpoints.
- `search.messages` returns the `channel` field as an object (`{"id", "name", ...}`) rather than the bare id used by history and replies endpoints.
- Slack returns `thread_ts: null` on a search result for a thread reply, so the permalink carries the true root in its `?thread_ts=` parameter.
- Slack decorates the same message differently between `search.messages` and `conversations.replies` (different `blocks` ids, signed URLs, team metadata, search-highlighted `text`), so caching both sources would oscillate.
- The existing schema (`threads` and `messages` tables) is reused; no schema change is needed beyond the optional `messages_fts` index.
- Full-text search is optional: the FTS5 index degrades to no results when the SQLite build lacks FTS5.

## Acceptance Criteria

Every FR and NFR shall have at least one acceptance criterion.

Order criteria by FRs first (sorted by ID), then NFRs (sorted by ID).

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: A query returns matching messages
      Given a Slack API returning matches for a query
      When the user runs `slackx conversations search "hello"`
      Then the command exits 0 and prints the matches
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Matched messages are cached under their thread
      Given a match with channel C1 and ts 1700000000.000100
      When the search completes
      Then the message is readable via `conversations get` with no further fetch
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: An object channel is normalized
      Given a match whose channel is `{"id": "C1", "name": "general"}`
      When the search completes
      Then the cached and rendered channel is `C1`
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: A reply match is filed under its root
      Given a match with `thread_ts` null and a permalink containing `thread_ts=1700000000.000100`
      When the search completes
      Then the thread is cached under `1700000000.000100` and not under the reply ts
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Results span several pages
      Given a Slack API reporting three pages of matches
      When the user runs the search
      Then every page is fetched and paging stops at the last page
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: A summary is printed to stderr
      Given a search returning matches
      When the command completes
      Then stderr reports the match count and the existing and new thread and message counts
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: A custom API base URL is used
      Given `--api-base-url` points at a local fake Slack server
      When the user runs the search
      Then the request is sent to that base URL
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Full threads are expanded
      Given a match belonging to a thread with replies
      When the user runs the search with `--full-threads`
      Then every reply in that thread is fetched and cached
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: The match limit caps fetching
      Given a Slack API with more matches than the limit
      When the user runs the search with `--limit 2`
      Then at most two matches are fetched
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: The page size is configurable
      Given the default page size of 20
      When the user runs the search with `--count 5`
      Then the request asks Slack for 5 results per page
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Result ordering is configurable
      Given a search
      When the user runs it with `--sort score --sort-dir asc`
      Then the request sends `sort=score` and `sort_dir=asc`
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: JSON and JSONL output
      Given matches exist
      When the user runs the search with `--json` or `--jsonl`
      Then the output is JSON or a single JSON line respectively
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Field selection and rejection
      Given the available search fields
      When the user runs with `--fields text,channel` then with `--fields bogus`
      Then the first emits only those fields in order and the second exits non-zero
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: Names are rendered from the cache
      Given cached users and channels covering a match
      When the user runs the search
      Then the output shows the user display name and channel name, and a direct channel shows the peer name
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: Full threads avoid double caching
      Given a match that also appears as the parent in `conversations.replies`
      When the user runs the search with `--full-threads` twice
      Then the second run reports zero new threads and zero new messages
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Paging always terminates
      Given a Slack API returning a repeated page number
      When the pager runs
      Then it stops instead of looping forever
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Full-thread replies are fetched concurrently
      Given several distinct matched threads
      When the user runs the search with `--full-threads`
      Then all thread replies are fetched concurrently and each thread commits separately
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Rate limits are honored
      Given Slack responds with a rate limit response
      When the search issues requests
      Then the client backs off per `Retry-After` before retrying
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Hostile local queries are safe
      Given a query that is only operators or whitespace
      When the local full-text search runs
      Then it returns no results without raising
    ```

- [ ] **NFR-5**

    ```gherkin
    @NFR-5
    Scenario: An unchanged rerun reports nothing new
      Given a search that was just run against unchanged data
      When the same search runs again
      Then it reports zero new threads and zero new messages
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should the local full-text search (`storage.search_messages`, exposed through the web UI `/api/search`) be documented here or under the Web UI feature?
2. Is `DEFAULT_SEARCH_LIMIT` of 200 the right default cap, or should it be configurable per invocation through config rather than only the `--limit` flag?
