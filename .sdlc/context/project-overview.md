<!-- session_link: http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ -->
# Project Overview

## Purpose

slackx (package `slackx`) is a single-user Python 3.13 command-line tool that caches Slack threads, channel messages, users, channels, and search results into a local SQLite database, one database per workspace. It fetches on demand through the Slack Web API over async httpx and stores everything with sqlite3, so cached conversations can be read offline and queried without a workspace export. It also serves a local FastAPI web UI (`serve`) to browse the cache in a Slack-like interface, and ships a built-in fake Slack API server for testing and development without hitting the real Slack API.

## Key Stakeholders

| Stakeholder | Role | Interest |
|---|---|---|
| Developer / researcher | Author and primary user | Reliable offline access to cached Slack conversations for analysis, archival, or reading |
| Slack workspace members | Data subjects | Their messages are fetched and stored locally |
| Cache consumers | Other local programs sharing one cache | Stable read markers so each consumer tracks its own last-read position without overwriting others |
| Maintainer | Repository owner | A working CLI, web UI, and fake server that pass CI |

Named individuals cannot be determined from the code alone. The author listed in pyproject.toml is Tom Rochette, and CODEOWNERS lists `@tomzx`.

## Scope

**In scope:**
- Fetching and caching individual Slack threads via permalink or explicit channel id and timestamp
- Incremental refresh of cached threads (only new replies and recent edits) via `oldest`
- Fetching channel message histories via conversations.history, with optional full thread reply expansion
- Live workspace search via search.messages, caching each match under its channel and thread
- Polling multiple channels concurrently for new messages
- Bulk caching of all workspace users and visible channels, plus single-entity refresh via users.info and conversations.info
- Read markers that track each consumer's last-read position in a channel or thread
- Local full-text search over cached messages using SQLite FTS5
- Human-readable, JSON, and JSONL output, with selectable fields
- A local web UI and JSON HTTP API (`serve`) to browse the cache, search it, and trigger refreshes when credentials are configured
- Cache inspection and clearing via `cache status` and `cache clear`
- Credential management via environment variables and a config file
- Per-workspace cache databases, with the workspace discovered automatically via auth.test
- A configurable API base URL and a fake Slack API server with deterministic data for testing

**Out of scope:**
- Writing or sending messages to Slack
- Real-time event streaming (Socket Mode, Events API)
- Simultaneous multi-token management (one set of credentials is configured at a time; each workspace keeps its own cache database)
- A hosted or multi-user production web service (the web UI is local, primarily read-only, and needs credentials only for live refresh)
- Caching of files, attachments, or reactions
- Analytics, telemetry, metrics, tracing, or dashboards

## Key Constraints

- Slack API rate limits: the client retries up to 5 times on HTTP 429 with exponential backoff based on the Retry-After header, and proactively throttles using X-RateLimit-Remaining
- Authentication requires either a bot token (xoxb) or a browser token (xoxc) with its matching d cookie (xoxd), both from the same browser session
- SQLite is single-writer, so concurrent writes from multiple processes are not supported
- The tool runs as a single-user CLI; the only server components are the local web UI (`serve`) and the built-in fake Slack API server for testing
- Python 3.13 or newer is required
- Full-text search depends on SQLite FTS5, which is optional and degrades gracefully when unavailable
