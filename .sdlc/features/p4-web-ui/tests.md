---
title: "Web UI and HTTP API"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Web UI and HTTP API

## Scope

This plan covers the FastAPI JSON API, the read-marker write routes, the refresh routes, and static SPA serving in `src/slackx/server/app.py`.
Tests live in `tests/test_server.py` and drive the app through the FastAPI `TestClient`, and the `serve` command registration and database resolution are covered in `tests/test_cli.py`.
Out of scope: the SPA JavaScript itself, uvicorn binding behavior, and live Slack network fetches (the refresh routes are only tested up to the no-credentials and unknown-channel guards).

## Unit Tests

`test_server.py` drives the app through `TestClient`, so its cases are integration-level; the rows below name the payload-shaping behavior each test asserts.

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | User display name joins the real name and handle | User with real name `Alice Smith` and name `alice` | `display_name` is `Alice Smith (alice)`; a user with only a name uses that name |
| TC-2 | Avatar picks the largest available profile image | Profile with `image_512` and `image_192`; a profile with no images | The 512 URL; `None` when no image exists |
| TC-3 | Channel summary resolves a direct-message peer name | Named channel `general` and direct channel `D1` with peer `U1` | `general` keeps its name; `D1` has `name` null, peer display name, and `is_im` true |
| TC-4 | Message serialization attaches the author display name | Channel root message authored by `U1` | Message `user_name` is the author's display name |
| TC-5 | Search hit resolves names and carries a snippet | Query `deploys` matching one cached message | Hit has channel name, author name, and a snippet containing the term |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-6 | Read workspace counters | Two users, three channels, four messages, three threads cached | Counts match and `db_path` ends with `.db` |
| TC-7 | List users | Users cached with profiles | `user_count` and per-user payloads |
| TC-8 | List channels with counts | Named and direct channels cached | Message and thread counts, display names, and `is_im` flags |
| TC-9 | Read channel messages with paging | Channel `C1` has two roots, one threaded | Newest first, author names, reply counts, and `has_more` driven by `before`/`limit` |
| TC-10 | Read one thread | Thread root with one reply cached | Both messages with resolved author names |
| TC-11 | Full-text search | One cached message contains `deploys` | One hit with channel, author, and snippet |
| TC-12 | Set a read pointer with a default timestamp | Channel `C1` has cached messages | Pointer `last_read_ts` is the newest cached message and `GET /api/read` lists it |
| TC-13 | Set a thread read pointer with an explicit timestamp | Channel `C1` exists | Stored `thread_ts` and `last_read_ts` match the request body |
| TC-14 | Delete read pointers at each scope | One reader has a channel pointer and a thread pointer | Each delete reports the removed count and clears only the targeted scope |
| TC-15 | Refresh routes without credentials | No credentials configured | Each refresh POST returns 503 with a no-credentials message |
| TC-16 | Refresh an unknown channel | Channel id not cached | 404 |
| TC-17 | Serve the SPA index | Built assets present | `/` returns HTML containing the Vue script and `/static/app.js` is served |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-18 | Slack-style deep links serve the SPA | Request `/archives/C1`, `/archives/C1/p1700000000000001`, and a threaded variant | Each returns the SPA HTML; `/archives` and an over-long path return 404 |
| TC-19 | `serve` command is registered | Run `slackx serve --help` | `serve` appears and accepts `--host` and `--port` |
| TC-20 | `serve` resolves a database before binding | Run `serve` with credentials, then without | With credentials it resolves via auth.test; without credentials it falls back to offline resolution |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-21 | Request messages for an unknown channel | 200 with an empty message list and a null channel name, because search can cache messages for a channel whose row was never fetched |
| TC-22 | Request an unknown thread | 404 with a message naming the thread and channel |
| TC-23 | Set a read pointer with a blank reader | 422 |
| TC-24 | Search with a hostile query string | No hits and no error; the FTS query is not injected |
| TC-25 | Refresh without credentials | 503 with a detail explaining that no Slack credentials are configured |
| TC-26 | Set a read pointer for a channel with no cached messages and no explicit ts | 404 |

## Test Infrastructure

- FastAPI `TestClient` used as a context manager so the app lifespan runs and `ensure_search_index` executes.
- A `db_path` fixture returns a temporary database under `tmp_path`.
- A `_populate` helper writes users, channels, threads, and messages covering named, private, direct, threaded, and standalone cases.
- A `client` fixture builds `create_app(db_path=...)` and populates the database.
- `monkeypatch` replaces `server_app.load_credentials` with an empty token to test the no-credentials path.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-19, TC-20 |
| FR-2 | TC-6 |
| FR-3 | TC-1, TC-2, TC-7 |
| FR-4 | TC-3, TC-8 |
| FR-5 | TC-4, TC-9, TC-21 |
| FR-6 | TC-10, TC-22 |
| FR-7 | TC-5, TC-11, TC-24 |
| FR-8 | TC-12, TC-13, TC-23, TC-26 |
| FR-9 | TC-14 |
| FR-10 | TC-16 |
| FR-11 | TC-17, TC-18 |
| FR-12 | TC-15, TC-25 |
| NFR-1 | TC-19 |
| NFR-2 | TC-6 |
| NFR-3 | TC-6, TC-11 |
| NFR-4 | TC-18 |
