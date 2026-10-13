---
title: "Web UI and HTTP API"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Requirements: Web UI and HTTP API

## Overview

The `serve` command exposes the local SQLite cache through a browser UI and a JSON API.
A FastAPI app serves a single-page application for browsing cached users, channels, messages, threads, and search results.
A small set of endpoints can set last-read pointers, and a few POST endpoints refresh the cache from Slack when credentials are configured.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Slack user | Browses the cached conversations in a Slack-like interface without using the terminal |
| Scripter | Reads the same cache over the `/api/*` JSON endpoints |
| Feature author | Refreshes stale cached data from the browser instead of running CLI fetches |

## Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall provide a `slackx serve` command that binds a host and port and serves the web UI and JSON API |
| FR-2 | Must | The system shall expose `GET /api/summary` returning the database path and counts of users, channels, messages, and threads |
| FR-3 | Must | The system shall expose `GET /api/users` returning the cached users with resolved display names and avatar URLs |
| FR-4 | Must | The system shall expose `GET /api/channels` returning cached channel summaries with message counts, thread counts, resolved display names, and a direct-message flag |
| FR-5 | Must | The system shall expose `GET /api/channels/{channel_id}/messages` returning the channel's root messages newest first, with author display names, reply counts, and `before`/`limit` paging |
| FR-6 | Must | The system shall expose `GET /api/channels/{channel_id}/threads/{thread_ts}` returning every cached message in the thread |
| FR-7 | Must | The system shall expose `GET /api/search` running a full-text search with a required query and a bounded limit, returning hits with resolved names and snippets |
| FR-8 | Must | The system shall expose `GET /api/read` and `PUT /api/read` to list and create or advance last-read pointers |
| FR-9 | Must | The system shall expose `DELETE` routes to delete a reader's pointers, a channel-level pointer, or one thread pointer |
| FR-10 | Must | The system shall expose POST refresh routes for users, channels, a channel, and a thread that run a live Slack fetch |
| FR-11 | Must | The system shall serve the single-page application at `/` and at Slack-style `/archives/{channel_id}` and `/archives/{channel_id}/{message_ref}` deep links, plus its `/static` assets |
| FR-12 | Should | The refresh routes shall report an error that the browser surfaces when no Slack credentials are configured, while browsing the existing cache stays available |

## Non-Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Security | The server shall bind to `127.0.0.1` by default so the cache is not exposed on the network |
| NFR-2 | Must | Performance | Each read request shall open a short-lived SQLite connection and serve from the local cache without a network call |
| NFR-3 | Should | Reliability | The system shall ensure the full-text search index exists at startup, and browsing shall keep working when the index is unavailable |
| NFR-4 | Should | Usability | Deep links shall use Slack permalink shape so a real Slack link path can be pasted after the serve host |

## Constraints

- The web UI source is not in this repository beyond the built assets in `web/dist`; only the built SPA is served.
- SQLite queries run on the event loop thread, matching the synchronous storage layer.
- The server is single-user and local; it has no user accounts or sessions.

## Acceptance Criteria

Every FR and NFR shall have at least one acceptance criterion.

Order criteria by FRs first (sorted by ID), then NFRs (sorted by ID).

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Start the server with default settings
      Given the cache database has cached data
      When the user runs `slackx serve`
      Then the server binds 127.0.0.1 on port 8280 and serves the UI
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Read workspace counters
      Given two users, three channels, four messages, and three threads are cached
      When the browser requests `GET /api/summary`
      Then the response reports those counts and a database path ending in `.db`
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: List users with display names and avatars
      Given a cached user has a real name, a name, and a profile image
      When the browser requests `GET /api/users`
      Then the user's `display_name` joins the real name and name, and `avatar` picks the largest available image
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: List channels with counts and a direct-message flag
      Given a named channel and a direct-message channel are cached
      When the browser requests `GET /api/channels`
      Then the named channel reports its name and counts, and the direct channel reports its peer's display name and `is_im` true
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Read a channel's messages with paging
      Given a channel has two root messages
      When the browser requests `GET /api/channels/C1/messages` with a `limit`
      Then messages are returned newest first with author names and reply counts, and `has_more` is true when the limit is reached
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Read one thread
      Given a thread has a root and one reply cached
      When the browser requests `GET /api/channels/C1/threads/1700000100.000002`
      Then both messages are returned with resolved author names
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Full-text search the cache
      Given a cached message contains the word deploys
      When the browser requests `GET /api/search?q=deploys`
      Then one hit is returned with its channel name, author name, and a snippet
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Set and list a last-read pointer
      Given a channel has cached messages
      When the browser sends `PUT /api/read` with a reader and channel and no timestamp
      Then the pointer's `last_read_ts` defaults to the newest cached message and `GET /api/read` lists it
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Delete read pointers at each scope
      Given a reader has a channel pointer and a thread pointer
      When the browser deletes the thread pointer, then the channel pointer, then the reader
      Then each delete reports the number of removed pointers and only the targeted scope is cleared
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Refresh a channel from the browser
      Given Slack credentials are configured and the channel is cached
      When the browser sends `POST /api/channels/C1/refresh`
      Then the channel's messages are fetched through the Slack client and a fetch result is returned
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Serve the SPA and a Slack deep link
      Given the built SPA assets are present
      When the browser requests `/` and `/archives/C1/p1700000100000003`
      Then both return the SPA HTML and `/static/app.js` is served
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: Refresh without credentials
      Given no Slack credentials are configured
      When the browser sends a refresh POST
      Then the server returns 503 with a message explaining that no credentials are configured
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Default bind address
      Given no host flag is passed
      When the user runs `slackx serve`
      Then the server binds 127.0.0.1 and is not reachable from another host on the network
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Read request stays local
      Given the server is running
      When the browser requests `GET /api/summary`
      Then the response is served from the local SQLite cache within the same event loop and no Slack request is made
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Search index ensured at startup
      Given a cache database created before the search index existed
      When the server starts
      Then the full-text index is created and search returns hits
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Permalink-shaped paths serve the SPA
      Given the server is running
      When the browser requests a path in Slack permalink shape such as `/archives/C1/p1700000100000003`
      Then the SPA is returned so the client can resolve the channel and message
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should the JSON API gain a generated OpenAPI document committed alongside the specification?
2. Should the server support an opt-in authentication token for non-localhost binding?
